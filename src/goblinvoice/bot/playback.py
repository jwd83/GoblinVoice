from __future__ import annotations

import asyncio
from pathlib import Path

import discord


class PlaybackManager:
    def __init__(self, *, ffmpeg_bin: str) -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self._guild_locks: dict[int, asyncio.Lock] = {}

    def _lock_for(self, guild_id: int) -> asyncio.Lock:
        lock = self._guild_locks.get(guild_id)
        if lock is None:
            lock = asyncio.Lock()
            self._guild_locks[guild_id] = lock
        return lock

    async def play_file(
        self,
        guild_id: int,
        voice_client: discord.VoiceClient,
        audio_path: Path,
    ) -> None:
        lock = self._lock_for(guild_id)
        async with lock:
            finished = asyncio.Event()
            loop = asyncio.get_running_loop()

            def _after(_: Exception | None) -> None:
                loop.call_soon_threadsafe(finished.set)

            source = discord.FFmpegOpusAudio(
                str(audio_path),
                executable=self.ffmpeg_bin,
                bitrate=96,
            )
            voice_client.play(source, after=_after)
            await finished.wait()
