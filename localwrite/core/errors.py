"""The single, app-wide way of reporting a failed AI request.

Every AI-related screen (correction popup, Writing Assistant, Home, Settings,
setup guide, tray) shows exactly the same short message. Details go only to the
technical log, and only the error *type* - never user text, prompts, model
output or raw server responses.
"""
from __future__ import annotations

import logging

AI_ERROR = "AI error"

log = logging.getLogger("localwrite.ai")


def report_ai_error(exc: BaseException | None = None, where: str = "") -> str:
    """Log a failed AI request safely and return the message every screen displays."""
    kind = type(exc).__name__ if exc is not None else "unknown"
    log.warning("AI request failed%s: %s", f" ({where})" if where else "", kind)
    return AI_ERROR
