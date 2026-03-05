from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from goblinvoice.api.app import create_app


def test_health_and_synthesize_contract(settings) -> None:
    app = create_app(settings)
    service = app.state.service
    service.set_user_default_backend(123, 99, "qwen3tts")
    service.set_user_default_voice(123, 99, "default")

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        payload = health.json()
        assert "queue" in payload
        assert "backends" in payload

        synth = client.post(
            "/synthesize",
            json={"guildId": 123, "text": "hello from goblin voice", "backend": "qwen3tts"},
        )
        assert synth.status_code == 200
        synth_payload = synth.json()
        assert synth_payload["backend"] == "qwen3tts"
        assert Path(synth_payload["audioPath"]).exists()

        preferred = client.post(
            "/synthesize",
            json={"guildId": 123, "userId": 99, "text": "hello from saved prefs"},
        )
        assert preferred.status_code == 200
        preferred_payload = preferred.json()
        assert preferred_payload["backend"] == "qwen3tts"
        assert Path(preferred_payload["audioPath"]).exists()

        voices = client.get("/voices/123")
        assert voices.status_code == 200
        voices_payload = voices.json()
        assert voices_payload["guildId"] == 123
        assert "builtin" in voices_payload
        assert "cloned" in voices_payload
        builtin = voices_payload["builtin"]
        assert isinstance(builtin, list)
        assert any(
            item.get("backend") == "pockettts" and item.get("voice_id") == "alba"
            for item in builtin
            if isinstance(item, dict)
        )


def test_clone_requires_consent(settings, tmp_path: Path) -> None:
    app = create_app(settings)
    sample_path = tmp_path / "sample.wav"
    sample_path.write_bytes(b"sample")

    with TestClient(app) as client:
        denied = client.post(
            "/clone",
            json={
                "guildId": 123,
                "name": "alice",
                "samplePath": str(sample_path),
                "consentToken": "missing",
                "target": "alice",
                "backend": "qwen3tts",
            },
        )
        assert denied.status_code == 400
        assert denied.json()["errorCode"] == "consent_invalid"

        consent = client.post(
            "/consent",
            json={"guildId": 123, "target": "alice", "issuedBy": "42"},
        )
        assert consent.status_code == 200
        token = consent.json()["token"]

        approved = client.post(
            "/clone",
            json={
                "guildId": 123,
                "name": "alice",
                "samplePath": str(sample_path),
                "consentToken": token,
                "target": "alice",
                "backend": "qwen3tts",
            },
        )
        assert approved.status_code == 200
        clone_payload = approved.json()
        assert clone_payload["backend"] == "qwen3tts"
        assert clone_payload["voiceId"]

        voices = client.get("/voices/123")
        assert voices.status_code == 200
        cloned = voices.json()["cloned"]
        assert any(
            item.get("voice_id") == clone_payload["voiceId"]
            for item in cloned
            if isinstance(item, dict)
        )
