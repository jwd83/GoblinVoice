from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from goblinvoice.adapters.qwen3tts import Qwen3TTSAdapter
from goblinvoice.errors import BackendError
from goblinvoice.types import CloneRequest, SynthesizeRequest


class _FakeModel:
    sample_rate = 22050
    prompts: list[str] = []

    @classmethod
    def load_model(cls, **_: object) -> "_FakeModel":
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
async def test_qwen3tts_synthesize_with_sdk_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Qwen3TTSAdapter(models_dir=tmp_path / "models", default_voice="default")
    fake_module = SimpleNamespace(TTSModel=_FakeModel)

    monkeypatch.setattr(adapter, "_import_qwen3_module", lambda: fake_module)
    monkeypatch.setattr(
        adapter,
        "_write_wav",
        lambda output_path, audio, sample_rate: output_path.write_bytes(b"wav"),
    )

    output_path = tmp_path / "out.wav"
    result = await adapter.synthesize(
        SynthesizeRequest(guild_id=1, text="hello from qwen tts", voice="default"),
        output_path,
    )

    assert result == output_path
    assert output_path.exists()
    assert _FakeModel.prompts == ["default"]


@pytest.mark.asyncio
async def test_qwen3tts_clone_uses_sample_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Qwen3TTSAdapter(models_dir=tmp_path / "models")
    fake_module = SimpleNamespace(TTSModel=_FakeModel)

    monkeypatch.setattr(adapter, "_import_qwen3_module", lambda: fake_module)

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

    assert profile.backend == "qwen3tts"
    assert Path(profile.sample_path) == sample.resolve()


@pytest.mark.asyncio
async def test_qwen3tts_healthcheck_uses_fallback_when_sdk_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True)
    adapter = Qwen3TTSAdapter(models_dir=models_dir)

    def _raise() -> object:
        raise BackendError("missing sdk", provider="qwen3tts")

    monkeypatch.setattr(adapter, "_import_qwen3_module", _raise)

    status = await adapter.healthcheck()
    assert status.reachable
    assert status.detail is not None
    assert "fallback_mode=true" in status.detail


@pytest.mark.asyncio
async def test_qwen3tts_synthesize_falls_back_to_tone_without_sdk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    adapter = Qwen3TTSAdapter(models_dir=tmp_path / "models")

    def _raise() -> object:
        raise BackendError("missing sdk", provider="qwen3tts")

    monkeypatch.setattr(adapter, "_import_qwen3_module", _raise)

    output_path = tmp_path / "fallback.wav"
    result = await adapter.synthesize(
        SynthesizeRequest(guild_id=1, text="fallback works", voice="default"),
        output_path,
    )

    assert result == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0
