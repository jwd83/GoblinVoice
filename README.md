# GoblinVoice

Python-only Discord TTS bot and API with pluggable voice backends, managed by `uv`.

## Quickstart

1. Install Python 3.11+ and `uv`.
2. Set required env vars in `.env`:
   - `DISCORD_TOKEN`
   - `GOBLINVOICE_SYSTEM_DEFAULT_BACKEND` (`pockettts` or `qwen3tts`)
   - Optional: `GOBLINVOICE_POCKETTTS_DEFAULT_VOICE` (default: `alba`)
3. Sync dependencies:

```bash
uv sync
```

PocketTTS loads its model on first use. If gated model access is required, set `HF_TOKEN` in `.env`.

## Run

```bash
uv run goblinvoice-api
uv run goblinvoice-bot
```

Or run both via process manager:

```bash
uv run goblinvoice --up
uv run goblinvoice --status
uv run goblinvoice --down
```

## Commands

- `/join`
- `/tts text voice? style? backend?`
- `/clone name sample_path consent_token backend?`
- `/cloneconsent target`
- `/voices`
- `/backend set provider`
- `/backend status`

`/voices` now shows both built-in voices by backend and guild cloned voices.

## Dev Checks

```bash
uv run python -m pytest
uv run ruff check .
uv run mypy src
```
