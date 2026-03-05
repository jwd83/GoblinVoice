from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from goblinvoice.adapters.pockettts import PocketTTSAdapter
from goblinvoice.errors import BackendError
from goblinvoice.types import CloneRequest, SynthesizeRequest


class _FakeModel:
    sample_rate = 22050
    prompts: list[str] = []

    @classmethod
    def load_model(cls) -> "_FakeModel":
        cls.prompts = []
        return cls()

    def get_state_for_audio_prompt(self, prompt: str) -> dict[str, str]:
        self.prompts.append(prompt)
        return {"prompt": prompt}

    def generate_audio(self, voice_state: dict[str, str], text: str) -> list[float]:
        assert voice_state["prompt"]
        assert text
        return [0.0, 0.2, -0.2, 0.0]


@pytest.mark.asyncio
async def test_pockettts_synthesize_with_sdk_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = PocketTTSAdapter(models_dir=tmp_path / "models", default_voice="alba")
    fake_module = SimpleNamespace(TTSModel=_FakeModel)

    monkeypatch.setattr(adapter, "_import_pocket_tts_module", lambda: fake_module)
    monkeypatch.setattr(
        adapter,
        "_write_wav",
        lambda output_path, audio, sample_rate: output_path.write_bytes(b"wav"),
    )

    output_path = tmp_path / "out.wav"
    result = await adapter.synthesize(
        SynthesizeRequest(guild_id=1, text="hello from pocket tts", voice="alba"),
        output_path,
    )

    assert result == output_path
    assert output_path.exists()
    assert _FakeModel.prompts == ["alba"]


@pytest.mark.asyncio
async def test_pockettts_clone_uses_sample_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = PocketTTSAdapter(models_dir=tmp_path / "models")
    fake_module = SimpleNamespace(TTSModel=_FakeModel)

    monkeypatch.setattr(adapter, "_import_pocket_tts_module", lambda: fake_module)

    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"sample")

    profile = await adapter.clone_voice(
        CloneRequest(
            guild_id=42,
            name="alice",
            sample_path=sample,
            consent_token="token",
            target="alice",
        ),
        tmp_path,
    )

    assert profile.backend == "pockettts"
    assert Path(profile.sample_path) == sample.resolve()


@pytest.mark.asyncio
async def test_pockettts_healthcheck_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    adapter = PocketTTSAdapter(models_dir=tmp_path / "models")

    def _raise() -> object:
        raise BackendError("missing sdk", provider="pockettts")

    monkeypatch.setattr(adapter, "_import_pocket_tts_module", _raise)

    status = await adapter.healthcheck()
    assert not status.reachable
