"""Writing modes and the instructions sent to the model for each one."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WritingMode:
    key: str
    label: str
    short: str
    description: str
    instruction: str
    strict: bool = False  # minimal-edit modes: low temperature, conservative example


_MODES = [
    WritingMode(
        "grammar", "Grammar Correction", "Grammar",
        "Fix grammar, spelling, punctuation and sentence construction",
        "Correct all grammar, spelling, punctuation and sentence-construction errors. Preserve the original "
        "meaning, tone, wording and style as much as possible; change only what is wrong or clearly awkward.",
        strict=True,
    ),
    WritingMode(
        "spelling", "Spelling Correction", "Spelling",
        "Fix misspelled words only, keep everything else",
        "Correct only misspelled words and obvious typos. Do NOT change grammar, word choice, punctuation, "
        "capitalization or sentence structure. Keep every correctly spelled word exactly as written.",
        strict=True,
    ),
    WritingMode(
        "quick", "Quick Fix", "Quick fix",
        "Fix obvious spelling and grammar slips without rewriting",
        "Fix only obvious spelling and grammar mistakes (typos, wrong verb forms, missing or doubled words). "
        "Do not rephrase, reorder or restyle anything; keep the user's wording, informal style, slang, "
        "abbreviations and emojis exactly as they are.",
        strict=True,
    ),
    WritingMode(
        "natural", "Natural English", "Natural",
        "Sound fluent, like a native speaker",
        "Rewrite the text so it sounds fluent and natural, the way a native English speaker would write it. "
        "Fix all errors. Keep the meaning, tone and approximate length.",
    ),
    WritingMode(
        "professional", "Professional Writing", "Professional",
        "Polished, professional English",
        "Rewrite the text in polished, professional English suitable for work communication. Fix all errors "
        "and use a courteous, confident tone. Do not invent facts, names, dates, promises or details.",
    ),
    WritingMode(
        "casual", "Casual Writing", "Casual",
        "Friendly and conversational",
        "Rewrite the text so it sounds natural, friendly and conversational, like a message to a colleague or "
        "friend. Fix all errors. Keep the meaning and do not add new information.",
    ),
    WritingMode(
        "clarity", "Improve Clarity", "Clarity",
        "Clearer and easier to understand",
        "Rewrite the text so it is clearer and easier to understand: use simple, direct sentences, remove "
        "ambiguity and fix all errors. Keep all of the original information and meaning.",
    ),
    WritingMode(
        "shorten", "Shorten Text", "Shorten",
        "Remove unnecessary words, keep the meaning",
        "Make the text shorter and more concise by removing unnecessary words, filler and repetition. Keep the "
        "essential meaning, all important information and the original tone. Fix any errors.",
    ),
    WritingMode(
        "expand", "Expand Text", "Expand",
        "Elaborate without inventing facts",
        "Expand the text into a fuller, more detailed version with smoother transitions and complete "
        "sentences. Elaborate only on ideas that are already present; never invent facts, numbers, names, "
        "dates or claims. Fix any errors.",
    ),
    WritingMode("custom", "Custom Instructions", "Custom", "Your own rewriting instructions", ""),
]

MODES: dict[str, WritingMode] = {m.key: m for m in _MODES}
MODE_ORDER: list[str] = [m.key for m in _MODES]
DEFAULT_MODE = "grammar"

# Modes from earlier versions mapped to their closest current equivalent.
LEGACY_MODES = {"improve": "clarity", "punctuation": "grammar"}


def get_mode(key: str) -> WritingMode:
    return MODES.get(LEGACY_MODES.get(key, key)) or MODES[DEFAULT_MODE]
