# GoblinVoice Cleanroom Target Plan (Full Python + UV)

## Product Outcome
GoblinVoice ships as a Python-only Discord voice application with pluggable TTS/clone adapters, managed entirely by `uv` for dependencies, environments, scripts, and lockfiles. Build a working bot with Pocket TTS and Qwen TTS local backends.

## Non-Negotiable Rules
- No TypeScript/Node runtime or build steps.
- One dependency system: `uv`.
- One lockfile at repo root: `uv.lock`.
- No project-local UV cache configuration (`UV_CACHE_DIR` and `uv.toml cache-dir` not used).
- Shared business logic called by both API and Discord command paths.

## Finished Repository Shape
- `pyproject.toml` (single source of package/dependency truth)
- `uv.lock`
- `src/goblinvoice/__init__.py`
- `src/goblinvoice/config.py`
- `src/goblinvoice/types.py`
- `src/goblinvoice/errors.py`
- `src/goblinvoice/orchestrator/service.py`
- `src/goblinvoice/orchestrator/backend_policy.py`
- `src/goblinvoice/orchestrator/job_queue.py`
- `src/goblinvoice/storage/filesystem.py`
- `src/goblinvoice/adapters/base.py`
- `src/goblinvoice/adapters/qwen3tts.py`
- `src/goblinvoice/adapters/pockettts.py`
- `src/goblinvoice/adapters/registry.py`
- `src/goblinvoice/api/app.py`
- `src/goblinvoice/api/schemas.py`
- `src/goblinvoice/bot/client.py`
- `src/goblinvoice/bot/commands.py`
- `src/goblinvoice/bot/playback.py`
- `tools/goblinvoice_tui.py`
- `tests/unit/...`
- `tests/integration/...`
- `voices/`, `models/`, `logs/`, `.pids/` (runtime data dirs)

## Runtime Components
- `goblinvoice-api`: FastAPI process exposing health and service endpoints.
- `goblinvoice-bot`: Discord bot process handling slash + text commands.
- Optional adapter-local workers are Python processes only.
- `goblinvoice` TUI process manager starts/stops/status for all Python services.

## Core Functional Behavior
- Commands:
  - `/join` Joins the channel of user. Reads all visible text in each users's chosen voice as TTS into voice channel
  - `/tts text voice? style? backend?`
  - `/clone name sample_path consent_token backend?`
  - `/cloneconsent target`
  - `/voices`
  - `/backend set provider`
  - `/backend status`
- Backend routing:
  - Request override, then guild default, then system default.
  - One fallback attempt on retryable backend error.
- Queue and timeout:
  - FIFO queue.
  - Single worker default.
  - Synthesize timeout 45s.
  - Clone timeout 90s.
- Consent:
  - Clone blocked without valid token.
  - Token consumption is one-time.
  - Consent/clone events appended to audit log.

## Data Contracts (Filesystem)
- `voices/guilds/<guildId>.json` for guild backend defaults.
- `voices/profiles/<guildId>/<voiceId>.json` for cloned voices.
- `voices/consents/<guildId>.json` for active consent tokens.
- `voices/audit/<guildId>.jsonl` append-only event history.
- All writes are atomic (`tmp` + rename) to avoid partial file corruption.

## API Surface (FastAPI)
- `GET /health`
- `POST /synthesize`
- `POST /clone`
- `POST /consent`
- `GET /voices/{guild_id}`
- `POST /backend/default`
- Error envelope:
  - `errorCode`
  - `message`
  - `retryable`
  - `provider` (optional)

## UV-Managed Developer Experience
- `uv sync`
- `uv run goblinvoice-api`
- `uv run goblinvoice-bot`
- `uv run goblinvoice --up`
- `uv run goblinvoice --status`
- `uv run goblinvoice --down`
- `uv run pytest`
- `uv run ruff check .`
- `uv run mypy src`

## pyproject.toml Shape
- Runtime deps:
  - `fastapi`
  - `uvicorn[standard]`
  - `discord.py`
  - `pydantic`
  - `pydantic-settings`
  - `httpx`
- Dev deps:
  - `pytest`
  - `pytest-asyncio`
  - `ruff`
  - `mypy`
- Console scripts:
  - `goblinvoice-api = goblinvoice.api.app:main`
  - `goblinvoice-bot = goblinvoice.bot.client:main`
  - `goblinvoice = tools.goblinvoice_tui:main`

## Config Model
- `.env` + typed settings in `config.py`.
- Required values:
  - `DISCORD_TOKEN`
  - `GOBLINVOICE_SYSTEM_DEFAULT_BACKEND`
- Optional values:
  - service ports/host
  - queue worker count
  - data directory overrides
  - adapter-specific tuning flags

## Testing Standard
- Unit tests:
  - backend policy
  - queue behavior/timeouts
  - consent validation
  - storage reads/writes and audit appends
- Integration tests:
  - API endpoint contracts
  - adapter registry wiring
  - bot command parsing and response formatting
- Smoke test:
  - start stack
  - synth request succeeds
  - clone request requires consent
  - health reports backend reachability

## Operations and Observability
- Structured JSON logs with request/job correlation id.
- Per-service log file in `logs/`.
- PID files in `.pids/`.
- Health checks include adapter reachability and queue pressure summary.

## Definition of Done
- Fresh clone setup is:
  - install Python + uv
  - `uv sync`
  - `uv run goblinvoice --up`
- All tests/lint/type checks run via `uv run`.
- Discord commands and API both hit the same orchestrator service behavior.
- Docs reflect only the Python + UV workflow.
