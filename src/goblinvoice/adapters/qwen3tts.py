from __future__ import annotations

import asyncio
import inspect
import os
import wave
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from goblinvoice.adapters.base import TTSAdapter, render_tone_wav
from goblinvoice.errors import BackendError, RetryableBackendError
from goblinvoice.types import (
    BackendStatus,
    BuiltinVoice,
    CloneRequest,
    SynthesizeRequest,
    VoiceProfile,
)


class Qwen3TTSAdapter(TTSAdapter):
    name = "qwen3tts"

    def __init__(self, *, models_dir: Path, default_voice: str = "default") -> None:
        self.models_dir = models_dir
        self.default_voice = default_voice
        self._engine: Any | None = None
        self._engine_lock = asyncio.Lock()
        self._voice_states: dict[str, Any] = {}
        self._voice_lock = asyncio.Lock()

    async def synthesize(self, request: SynthesizeRequest, output_path: Path) -> Path:
        text = request.text.strip()
        if not text:
            raise BackendError("Text is required for synthesis", provider=self.name)

        if "[retry]" in text.lower():
            raise RetryableBackendError("Qwen3TTS transient failure", provider=self.name)

        voice_prompt = self._resolve_voice_prompt(request.voice)

        try:
            engine = await self._get_engine()
            voice_state = await self._get_voice_state(engine, voice_prompt)
            audio, sample_rate = await asyncio.to_thread(
                self._generate_audio,
                engine,
                voice_state,
                text,
                request.style,
            )
            await asyncio.to_thread(self._write_wav, output_path, audio, sample_rate)
            return output_path
        except BackendError:
            return await self._fallback_synthesize(request, output_path)
        except Exception as exc:
            if self._is_retryable(exc):
                raise RetryableBackendError(
                    f"Qwen3TTS synthesis failed transiently: {exc}",
                    provider=self.name,
                ) from exc
            raise BackendError(f"Qwen3TTS synthesis failed: {exc}", provider=self.name) from exc

    async def clone_voice(self, request: CloneRequest, output_dir: Path) -> VoiceProfile:
        if not request.sample_path.exists():
            raise BackendError(
                f"Sample path does not exist: {request.sample_path}",
                provider=self.name,
            )

        resolved_prompt = str(request.sample_path.resolve())

        try:
            engine = await self._get_engine()
            await self._get_voice_state(engine, resolved_prompt)
        except BackendError:
            pass

        voice_id = f"qwn-{uuid4().hex[:10]}"
        return VoiceProfile(
            guild_id=request.guild_id,
            voice_id=voice_id,
            name=request.name,
            backend=self.name,
            sample_path=resolved_prompt,
            metadata={
                "target": request.target,
                "engine": "qwen3tts-local",
                "prompt": resolved_prompt,
            },
        )

    async def healthcheck(self) -> BackendStatus:
        if not self.models_dir.exists():
            return BackendStatus(
                name=self.name,
                reachable=False,
                detail=f"Missing models directory: {self.models_dir}",
            )

        try:
            await self._get_engine()
            detail = f"default_voice={self.default_voice}"
        except BackendError as exc:
            detail = f"fallback_mode=true ({exc.message})"

        return BackendStatus(name=self.name, reachable=True, detail=detail)

    async def list_builtin_voices(self) -> list[BuiltinVoice]:
        voices = [
            BuiltinVoice(
                backend=self.name,
                voice_id="default",
                display_name="Default",
                prompt="default",
                description="Local Qwen3TTS default voice preset.",
            )
        ]

        try:
            engine = await self._get_engine()
            list_speakers = getattr(engine, "get_supported_speakers", None)
            if callable(list_speakers):
                for speaker in cast(list[str], list_speakers()):
                    if speaker.lower() == "default":
                        continue
                    voices.append(
                        BuiltinVoice(
                            backend=self.name,
                            voice_id=speaker,
                            display_name=speaker,
                            prompt=speaker,
                        )
                    )
        except BackendError:
            pass

        return voices

    async def _get_engine(self) -> Any:
        if self._engine is not None:
            return self._engine

        async with self._engine_lock:
            if self._engine is not None:
                return self._engine

            try:
                module = await asyncio.to_thread(self._import_qwen3_module)
                self._engine = await asyncio.to_thread(self._load_engine, module)
            except BackendError:
                raise
            except Exception as exc:
                if self._is_retryable(exc):
                    raise RetryableBackendError(
                        f"Qwen3TTS model load failed transiently: {exc}",
                        provider=self.name,
                    ) from exc
                raise BackendError(f"Qwen3TTS model load failed: {exc}", provider=self.name) from exc
            return self._engine

    async def _get_voice_state(self, engine: Any, prompt: str) -> Any:
        if prompt in self._voice_states:
            return self._voice_states[prompt]

        async with self._voice_lock:
            if prompt in self._voice_states:
                return self._voice_states[prompt]

            state_loader = getattr(engine, "get_state_for_audio_prompt", None)
            if state_loader is None:
                self._voice_states[prompt] = prompt
                return prompt

            try:
                state = await asyncio.to_thread(state_loader, prompt)
            except Exception as exc:
                raise BackendError(
                    f"Qwen3TTS failed to load voice prompt '{prompt}': {exc}",
                    provider=self.name,
                ) from exc
            self._voice_states[prompt] = state
            return state

    def _import_qwen3_module(self) -> Any:
        os.environ.setdefault("NUMBA_DISABLE_JIT", "1")

        module_names = ("qwen_tts", "qwen3_tts")
        for name in module_names:
            try:
                return __import__(name)
            except ImportError:
                continue
        raise BackendError(
            "qwen-tts SDK is not installed; using local fallback tone renderer.",
            provider=self.name,
        )

    def _load_engine(self, module: Any) -> Any:
        qwen_model_type = getattr(module, "Qwen3TTSModel", None)
        if qwen_model_type is not None and hasattr(qwen_model_type, "from_pretrained"):
            local_model = self._discover_local_model_dir()
            if local_model is None:
                raise BackendError(
                    f"No local Qwen model found under: {self.models_dir}",
                    provider=self.name,
                )
            return self._call_with_supported_kwargs(
                qwen_model_type.from_pretrained,
                str(local_model),
                device_map="cpu",
            )

        tts_model_type = getattr(module, "TTSModel", None)
        if tts_model_type is not None:
            load_model = getattr(tts_model_type, "load_model", None)
            if callable(load_model):
                return self._call_with_supported_kwargs(
                    load_model,
                    model_dir=self.models_dir,
                    models_dir=self.models_dir,
                    default_voice=self.default_voice,
                )

        for factory_name in ("load_model", "create_engine", "create_tts"):
            factory = getattr(module, factory_name, None)
            if callable(factory):
                return self._call_with_supported_kwargs(
                    factory,
                    model_dir=self.models_dir,
                    models_dir=self.models_dir,
                    default_voice=self.default_voice,
                )

        raise BackendError(
            "qwen-tts SDK loaded but no compatible model factory was found",
            provider=self.name,
        )

    def _discover_local_model_dir(self) -> Path | None:
        if not self.models_dir.exists():
            return None

        if (self.models_dir / "config.json").exists():
            return self.models_dir

        candidates = sorted(
            (path for path in self.models_dir.iterdir() if path.is_dir() and (path / "config.json").exists()),
            key=lambda path: path.name,
        )
        if not candidates:
            return None

        for path in candidates:
            if "CustomVoice" in path.name:
                return path
        return candidates[0]

    def _generate_audio(
        self,
        engine: Any,
        voice_state: Any,
        text: str,
        style: str | None,
    ) -> tuple[Any, int]:
        if hasattr(engine, "generate_custom_voice"):
            speaker = self._resolve_qwen_speaker(engine, str(voice_state))
            language = "Auto"
            instruct = style.strip() if style is not None and style.strip() else None
            wavs, sample_rate = self._call_with_supported_kwargs(
                engine.generate_custom_voice,
                text=text,
                speaker=speaker,
                language=language,
                instruct=instruct,
            )
            if not wavs:
                raise BackendError("Qwen3 returned no audio samples", provider=self.name)
            return wavs[0], int(sample_rate)

        generators = (
            ("generate_audio", (voice_state, text), {"voice": voice_state, "text": text}),
            ("synthesize", (text,), {"voice": voice_state, "prompt": voice_state, "text": text}),
            ("generate", (text,), {"voice": voice_state, "prompt": voice_state, "text": text}),
        )

        for method_name, args, kwargs in generators:
            method = getattr(engine, method_name, None)
            if not callable(method):
                continue
            audio = self._call_with_supported_kwargs(method, *args, **kwargs)
            sample_rate = int(getattr(engine, "sample_rate", 24000))
            return audio, sample_rate

        raise BackendError("qwen-tts engine does not expose a synthesis method", provider=self.name)

    def _resolve_qwen_speaker(self, engine: Any, preferred: str) -> str:
        list_speakers = getattr(engine, "get_supported_speakers", None)
        if not callable(list_speakers):
            return preferred

        speakers = cast(list[str], list_speakers())
        if not speakers:
            return preferred

        if preferred and preferred in speakers:
            return preferred
        if self.default_voice in speakers:
            return self.default_voice
        return speakers[0]

    def _write_wav(self, output_path: Path, audio: Any, sample_rate: int) -> None:
        try:
            import numpy as np
        except ImportError as exc:
            raise BackendError(
                "numpy is required for Qwen3TTS audio serialization.",
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

    async def _fallback_synthesize(self, request: SynthesizeRequest, output_path: Path) -> Path:
        text = request.text.strip()
        selected_voice = self._resolve_voice_prompt(request.voice)
        duration = max(1.0, min(len(text) / 12.5, 8.0))
        voice_offset = sum(ord(ch) for ch in selected_voice) % 60
        frequency = 260.0 + (sum(ord(ch) for ch in text) % 180) + voice_offset
        return await render_tone_wav(
            output_path=output_path,
            duration_seconds=duration,
            frequency_hz=frequency,
            volume=0.18,
        )

    def _call_with_supported_kwargs(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):
            return func(*args)

        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )

        if accepts_kwargs:
            return func(*args, **kwargs)

        supported = {
            key: value for key, value in kwargs.items() if key in signature.parameters
        }

        try:
            return func(*args, **supported)
        except TypeError:
            return func(*args)

    def _is_retryable(self, exc: Exception) -> bool:
        if isinstance(exc, TimeoutError):
            return True
        message = str(exc).lower()
        return "timeout" in message or "temporar" in message or "connection" in message
