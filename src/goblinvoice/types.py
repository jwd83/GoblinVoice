from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def new_correlation_id() -> str:
    return uuid4().hex


@dataclass(slots=True)
class SynthesizeRequest:
    guild_id: int
    text: str
    user_id: int | None = None
    voice: str | None = None
    style: str | None = None
    backend: str | None = None
    correlation_id: str = field(default_factory=new_correlation_id)


@dataclass(slots=True)
class SynthesisResult:
    guild_id: int
    backend: str
    audio_path: Path
    correlation_id: str


@dataclass(slots=True)
class CloneRequest:
    guild_id: int
    name: str
    sample_path: Path
    consent_token: str
    target: str
    backend: str | None = None
    correlation_id: str = field(default_factory=new_correlation_id)


@dataclass(slots=True)
class VoiceProfile:
    guild_id: int
    voice_id: str
    name: str
    backend: str
    sample_path: str
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class UserPreferences:
    guild_id: int
    user_id: int
    backend: str | None = None
    voice: str | None = None
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BuiltinVoice:
    backend: str
    voice_id: str
    display_name: str
    prompt: str
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BackendStatus:
    name: str
    reachable: bool
    detail: str | None = None


@dataclass(slots=True)
class QueueSnapshot:
    pending: int
    inflight: int
    processed: int
    failed: int
