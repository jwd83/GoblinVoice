from __future__ import annotations

import pytest

from goblinvoice.bot.commands import parse_tts_command
from goblinvoice.errors import ValidationError


def test_parse_tts_command_text_only() -> None:
    text, backend = parse_tts_command('!tts "hello world"')

    assert text == "hello world"
    assert backend is None


def test_parse_tts_command_with_backend() -> None:
    text, backend = parse_tts_command('!tts "hello world" qwen3tts')

    assert text == "hello world"
    assert backend == "qwen3tts"


def test_parse_tts_command_rejects_missing_text() -> None:
    with pytest.raises(ValidationError):
        parse_tts_command("!tts")
