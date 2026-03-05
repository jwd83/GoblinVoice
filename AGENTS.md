# Repository Guidelines

## Project Structure & Module Organization
- `src/goblinvoice/`: application code.
  - `adapters/`: TTS backends (`pockettts`, `qwen3tts`) and registry wiring.
  - `orchestrator/`: backend selection, queueing, and service workflow.
  - `api/`: FastAPI app and request/response schemas.
  - `bot/`: Discord client, slash/text commands, playback.
  - `storage/`: filesystem persistence for guild/user settings, consent, audit.
- `tests/unit/` and `tests/integration/`: pytest suites.
- `voices/`, `models/`, `logs/`, `.pids/`: runtime/state directories (not source logic).
- `tools/`: local process manager (`goblinvoice_tui.py`).

## Build, Test, and Development Commands
- `uv sync`: install runtime + dev dependencies from `uv.lock`.
- `uv run goblinvoice-api`: start FastAPI service.
- `uv run goblinvoice-bot`: start Discord bot.
- `uv run goblinvoice --up|--status|--down`: manage local stack.
- `uv run pytest`: run all tests.
- `uv run ruff check .`: lint.
- `uv run mypy src`: strict type checks.

## Coding Style & Naming Conventions
- Python 3.11+ codebase; follow PEP 8 with 4-space indentation.
- Type hints are required for new/changed code; keep `mypy` strict-clean.
- Use `snake_case` for functions/variables/modules, `PascalCase` for classes.
- Keep adapters backend-agnostic at interfaces (`TTSAdapter`) and provider-specific internally.

## Testing Guidelines
- Framework: `pytest` with `pytest-asyncio` (`asyncio_mode=auto`).
- Place fast logic tests in `tests/unit/`; cross-module behavior in `tests/integration/`.
- Name files `test_*.py` and tests `test_*`.
- For adapter changes, add/adjust unit tests plus one integration path when behavior affects API/bot flow.

## Commit & Pull Request Guidelines
- Prefer clear imperative commit messages, e.g. `Add qwen-tts speaker discovery`.
- Avoid vague messages like `updates` or `working on`.
- Keep commits scoped (code + tests + required lockfile updates together).
- PRs should include:
  - What changed and why.
  - Test evidence (`uv run pytest` output summary).
  - Config/model notes (env vars, downloaded models, backend prerequisites).
