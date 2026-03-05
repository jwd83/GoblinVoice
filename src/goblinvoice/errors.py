from __future__ import annotations

from typing import Any


class GoblinVoiceError(Exception):
    error_code = "goblinvoice_error"

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        provider: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.provider = provider

    def to_envelope(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "errorCode": self.error_code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.provider:
            payload["provider"] = self.provider
        return payload


class ValidationError(GoblinVoiceError):
    error_code = "validation_error"


class NotFoundError(GoblinVoiceError):
    error_code = "not_found"


class ConsentError(GoblinVoiceError):
    error_code = "consent_invalid"


class BackendError(GoblinVoiceError):
    error_code = "backend_error"


class RetryableBackendError(BackendError):
    def __init__(self, message: str, *, provider: str | None = None) -> None:
        super().__init__(message, retryable=True, provider=provider)


class QueueError(GoblinVoiceError):
    error_code = "queue_error"
