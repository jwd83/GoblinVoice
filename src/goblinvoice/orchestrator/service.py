from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from goblinvoice.adapters.registry import AdapterRegistry, build_default_registry
from goblinvoice.config import Settings, load_settings
from goblinvoice.errors import BackendError, GoblinVoiceError, ValidationError
from goblinvoice.orchestrator.backend_policy import BackendPolicy
from goblinvoice.orchestrator.job_queue import JobQueue
from goblinvoice.storage.filesystem import FilesystemStore
from goblinvoice.types import (
    BuiltinVoice,
    CloneRequest,
    SynthesisResult,
    SynthesizeRequest,
    UserPreferences,
    VoiceProfile,
)

logger = logging.getLogger(__name__)


class GoblinVoiceService:
    def __init__(
        self,
        *,
        settings: Settings,
        store: FilesystemStore,
        registry: AdapterRegistry,
        queue: JobQueue,
        policy: BackendPolicy,
    ) -> None:
        self.settings = settings
        self.store = store
        self.registry = registry
        self.queue = queue
        self.policy = policy

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "GoblinVoiceService":
        resolved = settings or load_settings()
        store = FilesystemStore(resolved.voices_path)
        registry = build_default_registry(
            resolved.models_path,
            pocket_default_voice=resolved.pockettts_default_voice,
        )
        queue = JobQueue(worker_count=resolved.queue_worker_count)
        policy = BackendPolicy(system_default_backend=resolved.system_default_backend)
        return cls(settings=resolved, store=store, registry=registry, queue=queue, policy=policy)

    async def start(self) -> None:
        await self.queue.start()

    async def stop(self) -> None:
        await self.queue.stop()

    async def synthesize(self, request: SynthesizeRequest) -> SynthesisResult:
        available = self.registry.names()
        preferences = self.get_user_preferences(request.guild_id, request.user_id)
        backend_override = self._resolve_backend_override(
            request_backend=request.backend,
            preferences=preferences,
            available=available,
        )
        guild_default = self.store.get_guild_backend_default(request.guild_id)
        primary = self.policy.resolve(
            request_override=backend_override,
            guild_default=guild_default,
            available=available,
        )

        voice = request.voice
        if voice is None and preferences is not None:
            voice = preferences.voice

        resolved_request = request
        if voice != request.voice:
            resolved_request = SynthesizeRequest(
                guild_id=request.guild_id,
                text=request.text,
                user_id=request.user_id,
                voice=voice,
                style=request.style,
                backend=request.backend,
                correlation_id=request.correlation_id,
            )

        output_path = self._render_output_path(request.guild_id)
        try:
            await self._run_synthesize(primary, resolved_request, output_path)
            backend_used = primary
        except GoblinVoiceError as exc:
            fallback = self.policy.fallback(primary=primary, available=available)
            if exc.retryable and fallback is not None:
                logger.warning(
                    "Retryable backend error; using fallback",
                    extra={
                        "correlation_id": request.correlation_id,
                        "primary": primary,
                        "fallback": fallback,
                    },
                )
                await self._run_synthesize(fallback, resolved_request, output_path)
                backend_used = fallback
            else:
                raise

        return SynthesisResult(
            guild_id=request.guild_id,
            backend=backend_used,
            audio_path=output_path,
            correlation_id=request.correlation_id,
        )

    async def clone(self, request: CloneRequest) -> VoiceProfile:
        token_record = self.store.consume_consent_token(
            request.guild_id,
            token=request.consent_token,
            target=request.target,
        )
        self.store.append_audit_event(
            request.guild_id,
            {
                "event": "consent_consumed",
                "target": request.target,
                "issuedBy": token_record.get("issuedBy"),
                "correlationId": request.correlation_id,
            },
        )

        available = self.registry.names()
        guild_default = self.store.get_guild_backend_default(request.guild_id)
        primary = self.policy.resolve(
            request_override=request.backend,
            guild_default=guild_default,
            available=available,
        )

        try:
            profile = await self._run_clone(primary, request)
            backend_used = primary
        except GoblinVoiceError as exc:
            fallback = self.policy.fallback(primary=primary, available=available)
            if exc.retryable and fallback is not None:
                profile = await self._run_clone(fallback, request)
                backend_used = fallback
            else:
                self.store.append_audit_event(
                    request.guild_id,
                    {
                        "event": "clone_failed",
                        "backend": primary,
                        "error": str(exc),
                        "correlationId": request.correlation_id,
                    },
                )
                raise

        profile.backend = backend_used
        self.store.save_voice_profile(profile)
        self.store.append_audit_event(
            request.guild_id,
            {
                "event": "clone_created",
                "voiceId": profile.voice_id,
                "voiceName": profile.name,
                "backend": profile.backend,
                "target": request.target,
                "correlationId": request.correlation_id,
            },
        )
        return profile

    def create_consent(self, guild_id: int, *, target: str, issued_by: str) -> str:
        token = self.store.create_consent_token(guild_id, target=target, issued_by=issued_by)
        self.store.append_audit_event(
            guild_id,
            {
                "event": "consent_created",
                "token": token,
                "target": target,
                "issuedBy": issued_by,
            },
        )
        return token

    def list_voices(self, guild_id: int) -> list[VoiceProfile]:
        return self.store.list_voice_profiles(guild_id)

    async def list_voice_catalog(self, guild_id: int) -> dict[str, Any]:
        builtin: list[BuiltinVoice] = []
        for backend_name in self.registry.names():
            adapter = self.registry.get(backend_name)
            builtin.extend(await adapter.list_builtin_voices())

        cloned = self.store.list_voice_profiles(guild_id)
        return {
            "guildId": guild_id,
            "builtin": [voice.to_dict() for voice in builtin],
            "cloned": [voice.to_dict() for voice in cloned],
        }

    def set_guild_default_backend(self, guild_id: int, provider: str) -> None:
        normalized = provider.strip().lower()
        if normalized not in self.registry.names():
            raise ValidationError(f"Unknown backend: {provider}")
        self.store.set_guild_backend_default(guild_id, normalized)

    def set_user_default_backend(self, guild_id: int, user_id: int, provider: str) -> None:
        normalized = provider.strip().lower()
        if not normalized:
            raise ValidationError("Backend cannot be empty")
        if normalized not in self.registry.names():
            raise ValidationError(f"Unknown backend: {provider}")
        self.store.set_user_preferences(guild_id, user_id, backend=normalized)

    def set_user_default_voice(self, guild_id: int, user_id: int, voice: str) -> None:
        normalized = voice.strip()
        if not normalized:
            raise ValidationError("Voice cannot be empty")
        self.store.set_user_preferences(guild_id, user_id, voice=normalized)

    def get_user_preferences(self, guild_id: int, user_id: int | None) -> UserPreferences | None:
        if user_id is None:
            return None
        return self.store.get_user_preferences(guild_id, user_id)

    async def backend_status(self) -> list[dict[str, Any]]:
        statuses = await self.registry.statuses()
        return [
            {"name": item.name, "reachable": item.reachable, "detail": item.detail}
            for item in statuses
        ]

    async def health(self) -> dict[str, Any]:
        statuses = await self.backend_status()
        queue_state = self.queue.snapshot()
        return {
            "ok": all(status["reachable"] for status in statuses),
            "queue": {
                "pending": queue_state.pending,
                "inflight": queue_state.inflight,
                "processed": queue_state.processed,
                "failed": queue_state.failed,
            },
            "backends": statuses,
        }

    async def _run_synthesize(
        self,
        backend_name: str,
        request: SynthesizeRequest,
        output_path: Path,
    ) -> None:
        adapter = self.registry.get(backend_name)

        async def _run() -> Path:
            return await adapter.synthesize(request, output_path)

        await self.queue.submit(
            name=f"synthesize:{backend_name}",
            timeout_seconds=self.settings.synth_timeout_seconds,
            coro_factory=_run,
        )

    async def _run_clone(self, backend_name: str, request: CloneRequest) -> VoiceProfile:
        adapter = self.registry.get(backend_name)
        output_dir = self.store.profiles_dir / str(request.guild_id)

        async def _run() -> VoiceProfile:
            profile = await adapter.clone_voice(request, output_dir)
            if not profile.voice_id:
                raise BackendError("Adapter returned invalid voice profile", provider=backend_name)
            return profile

        result = await self.queue.submit(
            name=f"clone:{backend_name}",
            timeout_seconds=self.settings.clone_timeout_seconds,
            coro_factory=_run,
        )
        if not isinstance(result, VoiceProfile):
            raise BackendError("Clone adapter returned unexpected payload", provider=backend_name)
        return result

    def _render_output_path(self, guild_id: int) -> Path:
        render_dir = self.store.renders_dir / str(guild_id)
        render_dir.mkdir(parents=True, exist_ok=True)
        return render_dir / f"{uuid4().hex}.wav"

    def _resolve_backend_override(
        self,
        *,
        request_backend: str | None,
        preferences: UserPreferences | None,
        available: list[str],
    ) -> str | None:
        if request_backend is not None:
            return request_backend

        if preferences is None or preferences.backend is None:
            return None

        normalized = preferences.backend.strip().lower()
        normalized_available = {name.strip().lower() for name in available}
        if normalized in normalized_available:
            return normalized
        return None
