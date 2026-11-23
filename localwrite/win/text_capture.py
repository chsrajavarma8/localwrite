"""Capture the text the user has selected in another application.

Only runs when the user presses a LocalWrite shortcut. It simulates Ctrl+C,
reads the copied text, and (by default) restores the previous clipboard.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from localwrite.win import clipboard, keyboard_sim
from localwrite.win.window_info import WindowTarget, get_foreground_target

log = logging.getLogger(__name__)

MAX_CAPTURE_CHARS = 20_000


class CaptureError(Exception):
    def __init__(self, title: str, hint: str = "") -> None:
        super().__init__(title)
        self.title = title
        self.hint = hint


@dataclass(frozen=True)
class CaptureResult:
    text: str
    target: WindowTarget


def copy_current_selection(timeout_ms: int) -> str | None:
    """Send Ctrl+C to the foreground app and return the copied text (None = nothing copied)."""
    before = clipboard.sequence_number()
    keyboard_sim.send_copy()
    if not clipboard.wait_for_change(before, timeout_ms):
        return None
    time.sleep(0.03)  # let the app finish publishing all of its formats
    if clipboard.is_vscode_empty_selection_copy():
        return None
    return clipboard.get_text_with_retry()


def capture_selection(
    *, restore_clipboard: bool = True, timeout_ms: int = 900, target: WindowTarget | None = None
) -> CaptureResult:
    target = target or get_foreground_target()
    if target is None:
        raise CaptureError("No active window", "Click into the app you're typing in, select text, then press the shortcut.")
    if target.is_own_process:
        raise CaptureError(
            "Select text in another application",
            "LocalWrite corrects text in other apps. To try it here, open the Writing Assistant page.",
        )
    if target.is_terminal:
        raise CaptureError(
            "Terminal windows aren't supported",
            "In a terminal Ctrl+C would interrupt the running program. Copy the text yourself, then use "
            "'Correct clipboard text' from the tray menu.",
        )
    if not keyboard_sim.wait_for_modifiers_released(1.5):
        keyboard_sim.release_stuck_modifiers()

    with clipboard.lock:
        snap = None
        if restore_clipboard:
            try:
                snap = clipboard.snapshot()
            except clipboard.ClipboardError as exc:
                raise CaptureError(str(exc)) from exc
        try:
            text = copy_current_selection(timeout_ms)
        except OSError as exc:
            log.warning("SendInput failed: %s", exc)
            raise CaptureError(
                "Couldn't send the copy command",
                "The target app may be running as administrator. Run LocalWrite as administrator too, "
                "or copy the text and use 'Correct clipboard text'.",
            ) from exc
        finally:
            if snap is not None:
                try:
                    clipboard.restore(snap)
                except clipboard.ClipboardError:
                    log.warning("Clipboard restore after capture failed")

    if text is None:
        raise CaptureError(
            "No text selected",
            f"Highlight the text you want to correct in {target.app_label}, then press the shortcut again. "
            "If the app blocks copying, copy the text yourself and use 'Correct clipboard text'.",
        )
    if not text.strip():
        raise CaptureError("The selection is empty", "Select some words and try again.")
    if len(text) > MAX_CAPTURE_CHARS:
        raise CaptureError(
            "The selection is too long",
            f"{len(text):,} characters selected; the limit is {MAX_CAPTURE_CHARS:,}. Select a smaller part.",
        )
    return CaptureResult(text=text, target=target)
