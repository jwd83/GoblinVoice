from __future__ import annotations

from goblinvoice.adapters.registry import build_default_registry


async def test_default_registry_wiring(settings) -> None:
    registry = build_default_registry(settings.models_path)
    names = registry.names()

    assert names == ["pockettts", "qwen3tts"]

    statuses = await registry.statuses()
    assert len(statuses) == 2
    assert {status.name for status in statuses} == {"pockettts", "qwen3tts"}
