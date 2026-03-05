from __future__ import annotations

import pytest

from goblinvoice.errors import ValidationError
from goblinvoice.orchestrator.backend_policy import BackendPolicy


def test_backend_policy_prefers_request_override() -> None:
    policy = BackendPolicy(system_default_backend="pockettts")

    resolved = policy.resolve(
        request_override="qwen3tts",
        guild_default="pockettts",
        available=["pockettts", "qwen3tts"],
    )

    assert resolved == "qwen3tts"


def test_backend_policy_uses_guild_then_system_default() -> None:
    policy = BackendPolicy(system_default_backend="pockettts")

    resolved = policy.resolve(
        request_override=None,
        guild_default="qwen3tts",
        available=["pockettts", "qwen3tts"],
    )

    assert resolved == "qwen3tts"


def test_backend_policy_rejects_unknown_override() -> None:
    policy = BackendPolicy(system_default_backend="pockettts")

    with pytest.raises(ValidationError):
        policy.resolve(
            request_override="missing",
            guild_default=None,
            available=["pockettts", "qwen3tts"],
        )


def test_backend_policy_fallback_uses_system_default() -> None:
    policy = BackendPolicy(system_default_backend="pockettts")

    fallback = policy.fallback(primary="qwen3tts", available=["pockettts", "qwen3tts"])

    assert fallback == "pockettts"
