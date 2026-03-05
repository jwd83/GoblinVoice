from __future__ import annotations

from pathlib import Path

import pytest

from goblinvoice.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    models_root = tmp_path / "models"
    (models_root / "pockettts").mkdir(parents=True)
    (models_root / "qwen3tts").mkdir(parents=True)

    return Settings(
        DISCORD_TOKEN="test-token",
        GOBLINVOICE_SYSTEM_DEFAULT_BACKEND="pockettts",
        GOBLINVOICE_DATA_ROOT=str(tmp_path),
        GOBLINVOICE_VOICES_DIR="voices",
        GOBLINVOICE_MODELS_DIR="models",
        GOBLINVOICE_LOGS_DIR="logs",
        GOBLINVOICE_PIDS_DIR=".pids",
    )
