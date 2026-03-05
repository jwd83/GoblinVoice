from __future__ import annotations

from pathlib import Path

from goblinvoice.adapters.base import TTSAdapter
from goblinvoice.adapters.pockettts import PocketTTSAdapter
from goblinvoice.adapters.qwen3tts import Qwen3TTSAdapter
from goblinvoice.errors import NotFoundError, ValidationError
from goblinvoice.types import BackendStatus


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, TTSAdapter] = {}

    def register(self, adapter: TTSAdapter) -> None:
        name = adapter.name.strip().lower()
        if not name:
            raise ValidationError("Adapter name cannot be empty")
        self._adapters[name] = adapter

    def unregister(self, name: str) -> None:
        self._adapters.pop(name.strip().lower(), None)

    def get(self, name: str) -> TTSAdapter:
        key = name.strip().lower()
        adapter = self._adapters.get(key)
        if adapter is None:
            raise NotFoundError(f"Unknown backend: {name}")
        return adapter

    def names(self) -> list[str]:
        return sorted(self._adapters.keys())

    async def statuses(self) -> list[BackendStatus]:
        results: list[BackendStatus] = []
        for name in self.names():
            results.append(await self._adapters[name].healthcheck())
        return results


def build_default_registry(
    models_dir: Path,
    *,
    pocket_default_voice: str = "alba",
) -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register(
        PocketTTSAdapter(
            models_dir=models_dir / "pockettts",
            default_voice=pocket_default_voice,
        )
    )
    registry.register(Qwen3TTSAdapter(models_dir=models_dir / "qwen3tts"))
    return registry
