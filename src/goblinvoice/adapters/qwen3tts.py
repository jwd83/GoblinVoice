from __future__ import annotations

from pathlib import Path
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

    def __init__(self, *, models_dir: Path) -> None:
        self.models_dir = models_dir

    async def synthesize(self, request: SynthesizeRequest, output_path: Path) -> Path:
        text = request.text.strip()
        if not text:
            raise BackendError("Text is required for synthesis", provider=self.name)

        if "[retry]" in text.lower():
            raise RetryableBackendError("Qwen3TTS transient failure", provider=self.name)

        duration = max(1.0, min(len(text) / 12.5, 8.0))
        selected_voice = (request.voice or "default").strip().lower() or "default"
        voice_offset = sum(ord(ch) for ch in selected_voice) % 60
        frequency = 260.0 + (sum(ord(ch) for ch in text) % 180) + voice_offset
        return await render_tone_wav(
            output_path=output_path,
            duration_seconds=duration,
            frequency_hz=frequency,
            volume=0.18,
        )

    async def clone_voice(self, request: CloneRequest, output_dir: Path) -> VoiceProfile:
        if not request.sample_path.exists():
            raise BackendError(
                f"Sample path does not exist: {request.sample_path}",
                provider=self.name,
            )
        voice_id = f"qwn-{uuid4().hex[:10]}"
        return VoiceProfile(
            guild_id=request.guild_id,
            voice_id=voice_id,
            name=request.name,
            backend=self.name,
            sample_path=str(request.sample_path),
            metadata={"target": request.target, "engine": "qwen3tts-local"},
        )

    async def healthcheck(self) -> BackendStatus:
        reachable = self.models_dir.exists()
        detail = None if reachable else f"Missing models directory: {self.models_dir}"
        return BackendStatus(name=self.name, reachable=reachable, detail=detail)

    async def list_builtin_voices(self) -> list[BuiltinVoice]:
        return [
            BuiltinVoice(
                backend=self.name,
                voice_id="default",
                display_name="Default",
                prompt="default",
                description="Built-in synthetic preset for the local Qwen3 adapter.",
            )
        ]
