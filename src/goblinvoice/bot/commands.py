from __future__ import annotations

import logging
import shlex
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from goblinvoice.bot.playback import PlaybackManager
from goblinvoice.config import Settings
from goblinvoice.errors import GoblinVoiceError, ValidationError
from goblinvoice.orchestrator.service import GoblinVoiceService
from goblinvoice.types import CloneRequest, SynthesizeRequest

logger = logging.getLogger(__name__)


def parse_tts_command(content: str) -> tuple[str, str | None]:
    parts = shlex.split(content)
    if len(parts) < 2:
        raise ValidationError("Usage: !tts <text> [backend]")
    text = parts[1]
    backend = parts[2] if len(parts) >= 3 else None
    return text, backend


def register_commands(
    *,
    bot: commands.Bot,
    service: GoblinVoiceService,
    playback: PlaybackManager,
    settings: Settings,
) -> None:
    if not hasattr(bot, "reader_enabled_guilds"):
        bot.reader_enabled_guilds = set()  # type: ignore[attr-defined]

    @bot.tree.command(name="join", description="Join your current voice channel")
    async def join(interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.user is None:
            await interaction.response.send_message("Guild context required.", ephemeral=True)
            return

        voice_state = getattr(interaction.user, "voice", None)
        if voice_state is None or voice_state.channel is None:
            await interaction.response.send_message(
                "Join a voice channel first.",
                ephemeral=True,
            )
            return

        channel = voice_state.channel
        voice_client = interaction.guild.voice_client
        try:
            if isinstance(voice_client, discord.VoiceClient) and voice_client.is_connected():
                await voice_client.move_to(channel)
            else:
                await channel.connect()
        except RuntimeError as exc:
            message = str(exc)
            if "PyNaCl library needed" in message:
                await interaction.response.send_message(
                    "Voice support dependency is missing on host (`PyNaCl`). "
                    "Install deps with `uv sync` and restart bot.",
                    ephemeral=True,
                )
                return
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to join voice channel")
            await interaction.response.send_message(
                f"Failed to join voice channel: {exc}",
                ephemeral=True,
            )
            return

        bot.reader_enabled_guilds.add(interaction.guild.id)  # type: ignore[attr-defined]
        await interaction.response.send_message("Connected and ready.")

    @bot.tree.command(name="tts", description="Speak text in voice chat")
    async def tts(
        interaction: discord.Interaction,
        text: str,
        voice: str | None = None,
        style: str | None = None,
        backend: str | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Guild context required.", ephemeral=True)
            return

        voice_client = interaction.guild.voice_client
        if not isinstance(voice_client, discord.VoiceClient) or not voice_client.is_connected():
            await interaction.response.send_message(
                "Bot is not in a voice channel. Run /join first.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)
        try:
            result = await service.synthesize(
                SynthesizeRequest(
                    guild_id=interaction.guild.id,
                    text=text,
                    voice=voice,
                    style=style,
                    backend=backend,
                )
            )
            await playback.play_file(interaction.guild.id, voice_client, result.audio_path)
        except GoblinVoiceError as exc:
            await interaction.followup.send(exc.message, ephemeral=True)
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("TTS command failed")
            await interaction.followup.send(f"TTS failed: {exc}", ephemeral=True)
            return

        await interaction.followup.send(f"Spoke via `{result.backend}`.")

    @bot.tree.command(name="cloneconsent", description="Create one-time consent token")
    async def cloneconsent(interaction: discord.Interaction, target: str) -> None:
        if interaction.guild is None or interaction.user is None:
            await interaction.response.send_message("Guild context required.", ephemeral=True)
            return

        token = service.create_consent(
            interaction.guild.id,
            target=target,
            issued_by=str(interaction.user.id),
        )
        await interaction.response.send_message(
            f"Consent token for `{target}`: `{token}`",
            ephemeral=True,
        )

    @bot.tree.command(name="clone", description="Clone a voice from a sample file")
    async def clone(
        interaction: discord.Interaction,
        name: str,
        sample_path: str,
        consent_token: str,
        backend: str | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Guild context required.", ephemeral=True)
            return

        try:
            profile = await service.clone(
                CloneRequest(
                    guild_id=interaction.guild.id,
                    name=name,
                    sample_path=Path(sample_path),
                    consent_token=consent_token,
                    target=name,
                    backend=backend,
                )
            )
        except GoblinVoiceError as exc:
            await interaction.response.send_message(exc.message, ephemeral=True)
            return

        await interaction.response.send_message(
            f"Cloned voice `{profile.name}` as `{profile.voice_id}` via `{profile.backend}`."
        )

    @bot.tree.command(name="voices", description="List built-in and cloned voices for this guild")
    async def voices(interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Guild context required.", ephemeral=True)
            return

        catalog = await service.list_voice_catalog(interaction.guild.id)
        builtin_raw = catalog.get("builtin", [])
        cloned_raw = catalog.get("cloned", [])
        if not isinstance(builtin_raw, list) or not isinstance(cloned_raw, list):
            await interaction.response.send_message("Voice catalog is unavailable.", ephemeral=True)
            return

        grouped_builtin: dict[str, list[str]] = {}
        for entry in builtin_raw:
            if not isinstance(entry, dict):
                continue
            backend = entry.get("backend")
            voice_id = entry.get("voice_id")
            if not isinstance(backend, str) or not isinstance(voice_id, str):
                continue
            grouped_builtin.setdefault(backend, []).append(voice_id)

        lines: list[str] = []
        lines.append("Built-in voices:")
        if not grouped_builtin:
            lines.append("none")
        else:
            for backend in sorted(grouped_builtin):
                voices_for_backend = ", ".join(f"`{voice}`" for voice in grouped_builtin[backend])
                lines.append(f"{backend}: {voices_for_backend}")

        lines.append("")
        lines.append("Cloned voices:")
        if not cloned_raw:
            lines.append("none")
        else:
            for entry in cloned_raw:
                if not isinstance(entry, dict):
                    continue
                voice_id = entry.get("voice_id")
                name = entry.get("name")
                backend = entry.get("backend")
                if (
                    isinstance(voice_id, str)
                    and isinstance(name, str)
                    and isinstance(backend, str)
                ):
                    lines.append(f"`{voice_id}` | {name} | {backend}")

        lines.append("")
        lines.append("Use `/tts ... voice:<id> backend:<model>` to pick one.")

        await interaction.response.send_message("\n".join(lines))

    backend_group = app_commands.Group(name="backend", description="Backend controls")

    @backend_group.command(name="set", description="Set guild default backend")
    async def backend_set(interaction: discord.Interaction, provider: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Guild context required.", ephemeral=True)
            return

        try:
            service.set_guild_default_backend(interaction.guild.id, provider)
        except GoblinVoiceError as exc:
            await interaction.response.send_message(exc.message, ephemeral=True)
            return

        await interaction.response.send_message(f"Default backend set to `{provider}`")

    @backend_group.command(name="status", description="Show backend health")
    async def backend_status(interaction: discord.Interaction) -> None:
        statuses = await service.backend_status()
        lines = []
        for status in statuses:
            prefix = "OK" if status["reachable"] else "DOWN"
            detail = status.get("detail") or ""
            lines.append(f"{prefix} `{status['name']}` {detail}".strip())
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    bot.tree.add_command(backend_group)

    @bot.command(name="tts")
    async def tts_text(ctx: commands.Context[commands.Bot], *, content: str) -> None:
        if ctx.guild is None:
            return

        text, backend = parse_tts_command(f"!tts {content}")
        voice_client = ctx.guild.voice_client
        if not isinstance(voice_client, discord.VoiceClient) or not voice_client.is_connected():
            await ctx.send("Bot is not connected. Use /join first.")
            return

        result = await service.synthesize(
            SynthesizeRequest(guild_id=ctx.guild.id, text=text, backend=backend)
        )
        await playback.play_file(ctx.guild.id, voice_client, result.audio_path)
        await ctx.send(f"Spoke via `{result.backend}`")
