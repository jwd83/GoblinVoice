from __future__ import annotations

from pathlib import Path

import pytest

from goblinvoice.errors import ConsentError
from goblinvoice.storage.filesystem import FilesystemStore
from goblinvoice.types import VoiceProfile


def test_storage_round_trip_backend_and_voice(tmp_path: Path) -> None:
    store = FilesystemStore(tmp_path / "voices")
    store.set_guild_backend_default(123, "pockettts")

    assert store.get_guild_backend_default(123) == "pockettts"

    profile = VoiceProfile(
        guild_id=123,
        voice_id="voice-1",
        name="Goblin",
        backend="pockettts",
        sample_path="/tmp/sample.wav",
    )
    store.save_voice_profile(profile)

    voices = store.list_voice_profiles(123)
    assert len(voices) == 1
    assert voices[0].voice_id == "voice-1"


def test_consent_token_is_one_time(tmp_path: Path) -> None:
    store = FilesystemStore(tmp_path / "voices")
    token = store.create_consent_token(123, target="alice", issued_by="42")

    record = store.consume_consent_token(123, token=token, target="alice")
    assert record["issuedBy"] == "42"

    with pytest.raises(ConsentError):
        store.consume_consent_token(123, token=token, target="alice")


def test_audit_append_creates_jsonl(tmp_path: Path) -> None:
    store = FilesystemStore(tmp_path / "voices")
    store.append_audit_event(123, {"event": "consent_created", "target": "alice"})
    store.append_audit_event(123, {"event": "clone_created", "target": "alice"})

    audit_path = tmp_path / "voices" / "audit" / "123.jsonl"
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()

    assert len(lines) == 2
