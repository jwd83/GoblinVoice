from __future__ import annotations

import asyncio
import wave
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from goblinvoice.adapters.base import TTSAdapter
from goblinvoice.errors import BackendError, RetryableBackendError
from goblinvoice.types import (
    BackendStatus,
    BuiltinVoice,
    CloneRequest,
    SynthesizeRequest,
    VoiceProfile,
)


class PocketTTSAdapter(TTSAdapter):
    name = "pockettts"
    BUILTIN_VOICES: tuple[str, ...] = (
        "alba",
        "marius",
        "javert",
        "jean",
        "fantine",
        "cosette",
        "eponine",
        "azelma",
    )

    def __init__(self, *, models_dir: Path, default_voice: str = "alba") -> None:
        self.models_dir = models_dir
        self.default_voice = default_voice
        self._model: Any | None = None
        self._model_lock = asyncio.Lock()
        self._voice_states: dict[str, Any] = {}
        self._voice_lock = asyncio.Lock()

    async def synthesize(self, request: SynthesizeRequest, output_path: Path) -> Path:
        text = request.text.strip()
        if not text:
            raise BackendError("Text is required for synthesis", provider=self.name)

        voice_prompt = self._resolve_voice_prompt(request.voice)
        model = await self._get_model()
        voice_state = await self._get_voice_state(voice_prompt)

        try:
            audio = await asyncio.to_thread(model.generate_audio, voice_state, text)
        except Exception as exc:
            if self._is_retryable(exc):
                raise RetryableBackendError(
                    f"PocketTTS synthesis failed transiently: {exc}",
                    provider=self.name,
                ) from exc
            raise BackendError(f"PocketTTS synthesis failed: {exc}", provider=self.name) from exc

        sample_rate = int(getattr(model, "sample_rate", 24000))
        await asyncio.to_thread(self._write_wav, output_path, audio, sample_rate)
        return output_path

    async def clone_voice(self, request: CloneRequest, output_dir: Path) -> VoiceProfile:
        if not request.sample_path.exists():
            raise BackendError(
                f"Sample path does not exist: {request.sample_path}",
                provider=self.name,
            )

        resolved_prompt = str(request.sample_path.resolve())
        await self._get_voice_state(resolved_prompt)

        voice_id = f"pkt-{uuid4().hex[:10]}"
        return VoiceProfile(
            guild_id=request.guild_id,
            voice_id=voice_id,
            name=request.name,
            backend=self.name,
            sample_path=resolved_prompt,
            metadata={
                "target": request.target,
                "engine": "pockettts-local",
                "prompt": resolved_prompt,
            },
        )

    async def healthcheck(self) -> BackendStatus:
        try:
            await self._get_model()
        except BackendError as exc:
            return BackendStatus(name=self.name, reachable=False, detail=exc.message)
        return BackendStatus(
            name=self.name,
            reachable=True,
            detail=f"default_voice={self.default_voice}",
        )

    async def list_builtin_voices(self) -> list[BuiltinVoice]:
        voices: list[BuiltinVoice] = []
        for voice_id in self.BUILTIN_VOICES:
            voices.append(
                BuiltinVoice(
                    backend=self.name,
                    voice_id=voice_id,
                    display_name=voice_id.title(),
                    prompt=voice_id,
                )
            )
        return voices

    async def _get_model(self) -> Any:
        if self._model is not None:
            return self._model

        async with self._model_lock:
            if self._model is not None:
                return self._model

            try:
                module = await asyncio.to_thread(self._import_pocket_tts_module)
                tts_model_type = getattr(module, "TTSModel", None)
                if tts_model_type is None:
                    raise BackendError(
                        "pocket-tts is installed but TTSModel was not found",
                        provider=self.name,
                    )
                self._model = await asyncio.to_thread(tts_model_type.load_model)
            except BackendError:
                raise
            except Exception as exc:
                if self._is_retryable(exc):
                    raise RetryableBackendError(
                        f"PocketTTS model load failed transiently: {exc}",
                        provider=self.name,
                    ) from exc
                raise BackendError(
                    f"PocketTTS model load failed: {exc}",
                    provider=self.name,
                ) from exc
            return self._model

    async def _get_voice_state(self, prompt: str) -> Any:
        if prompt in self._voice_states:
            return self._voice_states[prompt]

        async with self._voice_lock:
            if prompt in self._voice_states:
                return self._voice_states[prompt]

            model = await self._get_model()
            try:
                state = await asyncio.to_thread(model.get_state_for_audio_prompt, prompt)
            except Exception as exc:
                raise BackendError(
                    f"PocketTTS failed to load voice prompt '{prompt}': {exc}",
                    provider=self.name,
                ) from exc

            self._voice_states[prompt] = state
            return state

    def _resolve_voice_prompt(self, request_voice: str | None) -> str:
        raw = (request_voice or self.default_voice).strip()
        if not raw:
            return self.default_voice
        if raw.startswith("hf://"):
            return raw

        prompt_path = Path(raw)
        if prompt_path.exists():
            return str(prompt_path.resolve())

        models_relative = self.models_dir / raw
        if models_relative.exists():
            return str(models_relative.resolve())

        return raw

    def _import_pocket_tts_module(self) -> Any:
        try:
            import pocket_tts  # type: ignore[import-untyped]
        except ImportError as exc:
            raise BackendError(
                "pocket-tts is not installed. Run `uv add pocket-tts`.",
                provider=self.name,
            ) from exc
        return pocket_tts

    def _write_wav(self, output_path: Path, audio: Any, sample_rate: int) -> None:
        try:
            import numpy as np
        except ImportError as exc:
            raise BackendError(
                "numpy is required for PocketTTS audio serialization.",
                provider=self.name,
            ) from exc

        pcm_data = self._to_int16_pcm(audio, np)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)

    def _to_int16_pcm(self, audio: Any, np: Any) -> bytes:
        if hasattr(audio, "detach"):
            audio = audio.detach()
        if hasattr(audio, "cpu"):
            audio = audio.cpu()
        if hasattr(audio, "numpy"):
            audio = audio.numpy()

        values = np.asarray(audio)
        if values.ndim == 0:
            values = values.reshape(1)
        if values.ndim > 1:
            values = values.reshape(-1)

        if np.issubdtype(values.dtype, np.integer):
            clipped = np.clip(values, -32768, 32767).astype(np.int16, copy=False)
            return cast(bytes, clipped.tobytes())

        float_values = values.astype(np.float32, copy=False)
        max_abs = float(np.max(np.abs(float_values))) if float_values.size else 0.0
        if max_abs > 1.5:
            pcm = np.clip(float_values, -32768.0, 32767.0).astype(np.int16)
            return cast(bytes, pcm.tobytes())

        pcm = (np.clip(float_values, -1.0, 1.0) * 32767.0).astype(np.int16)
        return cast(bytes, pcm.tobytes())

    def _is_retryable(self, exc: Exception) -> bool:
        if isinstance(exc, TimeoutError):
            return True
        message = str(exc).lower()
        return "timeout" in message or "temporar" in message or "connection" in message
