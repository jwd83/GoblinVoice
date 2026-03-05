from __future__ import annotations

import asyncio
import math
import wave
from abc import ABC, abstractmethod
from pathlib import Path

from goblinvoice.types import (
    BackendStatus,
    BuiltinVoice,
    CloneRequest,
    SynthesizeRequest,
    VoiceProfile,
)


class TTSAdapter(ABC):
    name: str

    @abstractmethod
    async def synthesize(self, request: SynthesizeRequest, output_path: Path) -> Path:
        raise NotImplementedError

    @abstractmethod
    async def clone_voice(self, request: CloneRequest, output_dir: Path) -> VoiceProfile:
        raise NotImplementedError

    @abstractmethod
    async def healthcheck(self) -> BackendStatus:
        raise NotImplementedError

    async def list_builtin_voices(self) -> list[BuiltinVoice]:
        return []


async def render_tone_wav(
    *,
    output_path: Path,
    duration_seconds: float,
    frequency_hz: float,
    volume: float = 0.2,
    sample_rate: int = 24000,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _write() -> None:
        total_samples = max(int(duration_seconds * sample_rate), 1)
        amplitude = int(32767 * volume)
        with wave.open(str(output_path), "w") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            frames = bytearray()
            for idx in range(total_samples):
                sample = math.sin(2.0 * math.pi * frequency_hz * idx / sample_rate)
                value = int(amplitude * sample)
                frames.extend(value.to_bytes(2, byteorder="little", signed=True))
            wav_file.writeframes(frames)

    await asyncio.to_thread(_write)
    return output_path
