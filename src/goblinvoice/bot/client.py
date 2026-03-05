from __future__ import annotations

import argparse
import json
import logging
from typing import Any

import discord
from discord.ext import commands

from goblinvoice.bot.commands import register_commands
from goblinvoice.bot.playback import PlaybackManager
from goblinvoice.config import Settings, load_settings
from goblinvoice.errors import GoblinVoiceError
from goblinvoice.orchestrator.service import GoblinVoiceService
from goblinvoice.types import SynthesizeRequest


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
        }
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(settings: Settings) -> None:
    settings.logs_path.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(settings.logs_path / "bot.log", encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [handler]


class GoblinVoiceBot(commands.Bot):
    def __init__(self, *, settings: Settings, service: GoblinVoiceService) -> None:
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings
        self.service = service
        self.playback = PlaybackManager(ffmpeg_bin=settings.ffmpeg_bin)
        self.reader_enabled_guilds: set[int] = set()

    async def setup_hook(self) -> None:
        await self.service.start()
        register_commands(
            bot=self,
            service=self.service,
            playback=self.playback,
            settings=self.settings,
        )
        await self.tree.sync()

    async def close(self) -> None:
        await self.service.stop()
        await super().close()

    async def on_ready(self) -> None:
        logging.getLogger(__name__).info("Bot connected as %s", self.user)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        await self.process_commands(message)

        guild = message.guild
        if guild is None or guild.id not in self.reader_enabled_guilds:
            return
        if not message.content.strip() or message.content.startswith("!"):
            return

        voice_client = guild.voice_client
        if not isinstance(voice_client, discord.VoiceClient) or not voice_client.is_connected():
            return

        try:
            result = await self.service.synthesize(
                SynthesizeRequest(
                    guild_id=guild.id,
                    text=f"{message.author.display_name} says {message.content}",
                )
            )
            await self.playback.play_file(guild.id, voice_client, result.audio_path)
        except GoblinVoiceError:
            logging.getLogger(__name__).exception("Failed to synthesize relay message")


def build_bot(settings: Settings | None = None) -> GoblinVoiceBot:
    resolved = settings or load_settings()
    configure_logging(resolved)
    service = GoblinVoiceService.from_settings(resolved)
    return GoblinVoiceBot(settings=resolved, service=service)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GoblinVoice Discord bot")
    parser.add_argument("--token", default=None)
    args = parser.parse_args()

    settings = load_settings()
    bot = build_bot(settings)
    bot.run(args.token or settings.discord_token)


if __name__ == "__main__":
    main()
