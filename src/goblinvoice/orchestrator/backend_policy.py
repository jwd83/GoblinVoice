from __future__ import annotations

from goblinvoice.errors import ValidationError


class BackendPolicy:
    def __init__(self, *, system_default_backend: str) -> None:
        self.system_default_backend = system_default_backend.strip().lower()

    def resolve(
        self,
        *,
        request_override: str | None,
        guild_default: str | None,
        available: list[str],
    ) -> str:
        if not available:
            raise ValidationError("No TTS backends are registered")

        normalized_available = [name.lower() for name in available]

        if request_override:
            candidate = request_override.strip().lower()
            if candidate in normalized_available:
                return candidate
            raise ValidationError(f"Requested backend is not available: {request_override}")

        if guild_default:
            candidate = guild_default.strip().lower()
            if candidate in normalized_available:
                return candidate

        if self.system_default_backend in normalized_available:
            return self.system_default_backend

        return normalized_available[0]

    def fallback(self, *, primary: str, available: list[str]) -> str | None:
        normalized_available = [name.lower() for name in available]
        if len(normalized_available) < 2:
            return None

        if (
            self.system_default_backend in normalized_available
            and self.system_default_backend != primary.lower()
        ):
            return self.system_default_backend

        for name in normalized_available:
            if name != primary.lower():
                return name
        return None
