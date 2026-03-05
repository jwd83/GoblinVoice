from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import RLock
from typing import Any, cast
from uuid import uuid4

from goblinvoice.errors import ConsentError
from goblinvoice.types import VoiceProfile, utc_now_iso


class FilesystemStore:
    def __init__(self, voices_dir: Path) -> None:
        self.voices_dir = voices_dir
        self.guild_dir = voices_dir / "guilds"
        self.profiles_dir = voices_dir / "profiles"
        self.consents_dir = voices_dir / "consents"
        self.audit_dir = voices_dir / "audit"
        self.renders_dir = voices_dir / "renders"
        self._lock = RLock()
        self.ensure_layout()

    def ensure_layout(self) -> None:
        for path in (
            self.voices_dir,
            self.guild_dir,
            self.profiles_dir,
            self.consents_dir,
            self.audit_dir,
            self.renders_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _atomic_write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f".{uuid4().hex}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, path)

    def _read_json(self, path: Path, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            return default
        return cast(dict[str, Any], loaded)

    def guild_backend_path(self, guild_id: int) -> Path:
        return self.guild_dir / f"{guild_id}.json"

    def set_guild_backend_default(self, guild_id: int, backend: str) -> None:
        payload = {"guildId": guild_id, "backend": backend, "updatedAt": utc_now_iso()}
        with self._lock:
            self._atomic_write_json(self.guild_backend_path(guild_id), payload)

    def get_guild_backend_default(self, guild_id: int) -> str | None:
        payload = self._read_json(self.guild_backend_path(guild_id), default={})
        backend = payload.get("backend")
        if isinstance(backend, str) and backend:
            return backend
        return None

    def save_voice_profile(self, profile: VoiceProfile) -> Path:
        path = self.profiles_dir / str(profile.guild_id) / f"{profile.voice_id}.json"
        with self._lock:
            self._atomic_write_json(path, profile.to_dict())
        return path

    def list_voice_profiles(self, guild_id: int) -> list[VoiceProfile]:
        guild_path = self.profiles_dir / str(guild_id)
        if not guild_path.exists():
            return []

        voices: list[VoiceProfile] = []
        for entry in sorted(guild_path.glob("*.json")):
            data = self._read_json(entry, default={})
            if not data:
                continue
            voice_id = data.get("voice_id") or data.get("voiceId")
            name = data.get("name")
            backend = data.get("backend")
            sample_path = data.get("sample_path") or data.get("samplePath")
            if not all(
                isinstance(field, str) and field
                for field in (voice_id, name, backend, sample_path)
            ):
                continue
            created_at_value = data.get("created_at")
            created_at = created_at_value if isinstance(created_at_value, str) else utc_now_iso()
            metadata_value = data.get("metadata")
            metadata = metadata_value if isinstance(metadata_value, dict) else {}
            voice_id_str = cast(str, voice_id)
            name_str = cast(str, name)
            backend_str = cast(str, backend)
            sample_path_str = cast(str, sample_path)
            voices.append(
                VoiceProfile(
                    guild_id=guild_id,
                    voice_id=voice_id_str,
                    name=name_str,
                    backend=backend_str,
                    sample_path=sample_path_str,
                    created_at=created_at,
                    metadata=metadata,
                )
            )
        return voices

    def _consents_path(self, guild_id: int) -> Path:
        return self.consents_dir / f"{guild_id}.json"

    def create_consent_token(
        self,
        guild_id: int,
        *,
        target: str,
        issued_by: str,
        ttl_seconds: int = 3600,
    ) -> str:
        token = uuid4().hex
        payload = self._read_json(self._consents_path(guild_id), default={"tokens": {}})
        tokens = payload.setdefault("tokens", {})
        if not isinstance(tokens, dict):
            tokens = {}
            payload["tokens"] = tokens

        issued_at = utc_now_iso()
        expires_at_epoch = int(time.time()) + ttl_seconds
        tokens[token] = {
            "target": target,
            "issuedBy": issued_by,
            "issuedAt": issued_at,
            "expiresAtEpoch": expires_at_epoch,
        }
        with self._lock:
            self._atomic_write_json(self._consents_path(guild_id), payload)
        return token

    def consume_consent_token(self, guild_id: int, *, token: str, target: str) -> dict[str, Any]:
        consents_path = self._consents_path(guild_id)
        with self._lock:
            payload = self._read_json(consents_path, default={"tokens": {}})
            tokens = payload.get("tokens")
            if not isinstance(tokens, dict):
                raise ConsentError("No consent tokens are active for this guild")

            record = tokens.get(token)
            if not isinstance(record, dict):
                raise ConsentError("Consent token is invalid or already consumed")

            record_target = record.get("target")
            if not isinstance(record_target, str) or (
                record_target.strip().casefold() != target.strip().casefold()
            ):
                raise ConsentError("Consent token target does not match")

            expires = record.get("expiresAtEpoch")
            if isinstance(expires, int):
                now_epoch = int(time.time())
                if now_epoch > expires:
                    tokens.pop(token, None)
                    self._atomic_write_json(consents_path, payload)
                    raise ConsentError("Consent token has expired")

            tokens.pop(token, None)
            self._atomic_write_json(consents_path, payload)
        return record

    def append_audit_event(self, guild_id: int, event: dict[str, Any]) -> None:
        audit_path = self.audit_dir / f"{guild_id}.jsonl"
        payload = dict(event)
        payload.setdefault("ts", utc_now_iso())
        line = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        with self._lock:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with audit_path.open("a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")
