from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    discord_token: str = Field("dev-token", alias="DISCORD_TOKEN")
    system_default_backend: str = Field(
        "pockettts",
        alias="GOBLINVOICE_SYSTEM_DEFAULT_BACKEND",
    )

    api_host: str = Field("127.0.0.1", alias="GOBLINVOICE_API_HOST")
    api_port: int = Field(8080, alias="GOBLINVOICE_API_PORT")

    queue_worker_count: int = Field(1, alias="GOBLINVOICE_QUEUE_WORKER_COUNT")
    synth_timeout_seconds: float = Field(45.0, alias="GOBLINVOICE_SYNTH_TIMEOUT_SECONDS")
    clone_timeout_seconds: float = Field(90.0, alias="GOBLINVOICE_CLONE_TIMEOUT_SECONDS")

    data_root: Path = Field(Path("."), alias="GOBLINVOICE_DATA_ROOT")
    voices_dir: Path = Field(Path("voices"), alias="GOBLINVOICE_VOICES_DIR")
    models_dir: Path = Field(Path("models"), alias="GOBLINVOICE_MODELS_DIR")
    logs_dir: Path = Field(Path("logs"), alias="GOBLINVOICE_LOGS_DIR")
    pids_dir: Path = Field(Path(".pids"), alias="GOBLINVOICE_PIDS_DIR")

    ffmpeg_bin: str = Field("ffmpeg", alias="GOBLINVOICE_FFMPEG_BIN")
    pockettts_default_voice: str = Field("alba", alias="GOBLINVOICE_POCKETTTS_DEFAULT_VOICE")

    @field_validator("system_default_backend")
    @classmethod
    def _normalize_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("GOBLINVOICE_SYSTEM_DEFAULT_BACKEND cannot be empty")
        return normalized

    @field_validator("queue_worker_count")
    @classmethod
    def _validate_workers(cls, value: int) -> int:
        if value < 1:
            raise ValueError("GOBLINVOICE_QUEUE_WORKER_COUNT must be >= 1")
        return value

    @field_validator("pockettts_default_voice")
    @classmethod
    def _validate_pockettts_default_voice(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("GOBLINVOICE_POCKETTTS_DEFAULT_VOICE cannot be empty")
        return normalized

    def resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return (self.data_root / path).resolve()

    @property
    def voices_path(self) -> Path:
        return self.resolve_path(self.voices_dir)

    @property
    def models_path(self) -> Path:
        return self.resolve_path(self.models_dir)

    @property
    def logs_path(self) -> Path:
        return self.resolve_path(self.logs_dir)

    @property
    def pids_path(self) -> Path:
        return self.resolve_path(self.pids_dir)

    @property
    def api_base_url(self) -> str:
        return f"http://{self.api_host}:{self.api_port}"


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
