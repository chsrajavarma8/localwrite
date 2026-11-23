import pytest

from localwrite.core.cancel import CancelToken
from localwrite.core.correction_engine import (
    CorrectionEngine, CustomInstructionRequired, build_messages, clean_output, split_into_chunks,
)
from localwrite.core.modes import MODES
from localwrite.core.ollama_client import EmptyResponseError


def test_every_mode_builds_messages():
    for key in MODES:
        msgs = build_messages("hello wrld", key, custom_instruction="make it pirate speak")
        assert msgs[0]["role"] == "system"
        assert "<text>\nhello wrld\n</text>" in msgs[-1]["content"]


def test_custom_requires_instruction():
    with pytest.raises(CustomInstructionRequired):
        build_messages("x", "custom", "")


@pytest.mark.parametrize("raw,expected", [
    ("I have an apple.", "I have an apple."),
    ("Here is the corrected text:\nI have an apple.", "I have an apple."),
    ("Corrected text: I have an apple.", "I have an apple."),
    ("Sure! Here's the revised version:\n\nI have an apple.", "I have an apple."),
    ('"I have an apple."', "I have an apple."),
    ("```\nI have an apple.\n```", "I have an apple."),
    ("<text>\nI have an apple.\n</text>", "I have an apple."),
    ("<think>the user wants...</think>\nI have an apple.", "I have an apple."),
    ("I have an apple.\n\nNote: I changed 'has' to 'have'.", "I have an apple."),
])
def test_clean_output(raw, expected):
    assert clean_output(raw, "I has a apple.") == expected


def test_clean_output_keeps_legit_prefix_and_quotes():
    original = "Here is the plan: we meet at 5."
    assert clean_output("Here is the plan: we meet at five.", original) == "Here is the plan: we meet at five."
    quoted = '"Hello," she said.'
    assert clean_output('"Hello," she said.', quoted) == '"Hello," she said.'


def test_clean_output_preserves_outer_whitespace_and_crlf():
    assert clean_output("Fixed text.", "  teh text.\n") == "  Fixed text.\n"
    assert clean_output("Line one.\nLine two.", "line one\r\nline two") == "Line one.\r\nLine two."


def test_clean_output_empty_raises():
    with pytest.raises(EmptyResponseError):
        clean_output("   ", "abc")


def test_chunking_roundtrip():
    para = "This is a sentence. " * 40
    text = "\n\n".join([para] * 6)
    chunks = split_into_chunks(text, 1000)
    assert "".join(chunks) == text
    assert all(len(c) <= 1000 for c in chunks)
    assert split_into_chunks("short", 1000) == ["short"]
    blob = "x" * 2500
    assert "".join(split_into_chunks(blob, 1000)) == blob


class FakeClient:
    def __init__(self, reply="I have an apple."):
        self.reply = reply
        self.calls = []

    def chat(self, model, messages, **kw):
        self.calls.append((model, messages, kw))
        for ch in self.reply:
            if kw.get("on_token"):
                kw["on_token"](ch)
        return self.reply


def test_engine_uses_strict_temperature_and_streams():
    client = FakeClient()
    eng = CorrectionEngine(client, "m", temperature=0.7)
    progress = []
    res = eng.correct("I has a apple.", "spelling", on_progress=progress.append, cancel=CancelToken())
    assert res.corrected == "I have an apple."
    assert res.changed
    assert client.calls[0][2]["temperature"] <= 0.15
    assert progress[-1] == "I have an apple."


def test_engine_rejects_empty_and_long():
    eng = CorrectionEngine(FakeClient(), "m")
    with pytest.raises(Exception):
        eng.correct("   ", "grammar")
    with pytest.raises(Exception):
        eng.correct("a" * 30000, "grammar")
