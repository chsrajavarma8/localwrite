"""Safely replace the user's selection in the original application.

Safety checks before pasting:
1. The original window still exists and belongs to the same process.
2. It can be brought back to the foreground.
3. (Optional, on by default) The current selection still contains exactly the
   text that was captured: we copy it again and compare.
If any check fails, nothing is pasted - the corrected text is put on the
clipboard instead and the user is told so.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from enum import Enum

from localwrite.win import clipboard, keyboard_sim
from localwrite.win import winapi as w
from localwrite.win.text_capture import copy_current_selection
from localwrite.win.window_info import WindowTarget, focus_window, foreground_root, is_window_alive

log = logging.getLogger(__name__)


class ReplaceOutcome(Enum):
    REPLACED = "replaced"
    COPIED = "copied"   # fell back to putting the text on the clipboard
    FAILED = "failed"


@dataclass(frozen=True)
class ReplaceResult:
    outcome: ReplaceOutcome
    message: str


def _normalize(text: str) -> str:
    return re.sub(r"[ \t]+\n", "\n", (text or "").replace("\r\n", "\n").replace("\r", "\n")).strip()


def _fallback(new_text: str, reason: str) -> ReplaceResult:
    try:
        clipboard.set_text(new_text, transient=False)
    except clipboard.ClipboardError as exc:
        return ReplaceResult(ReplaceOutcome.FAILED, f"{reason} Copying to the clipboard also failed: {exc}")
    return ReplaceResult(
        ReplaceOutcome.COPIED,
        f"{reason} The corrected text is on your clipboard - click where you want it and press Ctrl+V.",
    )


def replace_selection(
    target: WindowTarget,
    original_text: str,
    new_text: str,
    *,
    verify: bool = True,
    restore_clipboard: bool = True,
    restore_delay_ms: int = 600,
    copy_timeout_ms: int = 900,
    select_all_first: bool = False,
) -> ReplaceResult:
    if not is_window_alive(target):
        return _fallback(new_text, f"The original {target.app_label} window was closed.")
    if not focus_window(target):
        return _fallback(new_text, f"Couldn't switch back to {target.app_label}.")
    time.sleep(0.08)  # give the app a moment to restore keyboard focus to its text field
    if not keyboard_sim.wait_for_modifiers_released(1.5):
        keyboard_sim.release_stuck_modifiers()

    if select_all_first and target.focus_hwnd:
        # Real-time mode corrects the whole field: select it all through the control itself.
        result = w.ULONG_PTR(0)
        w.SendMessageTimeoutW(target.focus_hwnd, w.EM_SETSEL, 0, -1, w.SMTO_ABORTIFHUNG, 300, result)

    with clipboard.lock:
        try:
            snap = clipboard.snapshot() if restore_clipboard else None
        except clipboard.ClipboardError:
            snap = None
        try:
            if verify:
                current = copy_current_selection(copy_timeout_ms)
                if current is None or _normalize(current) != _normalize(original_text):
                    log.debug("Replace aborted: selection changed")
                    if snap is not None:
                        clipboard.restore(snap)
                        snap = None
                    return _fallback(new_text, "The selected text changed since the correction was requested, so it "
                                               "wasn't replaced automatically.")
            if foreground_root() != target.hwnd:
                return _fallback(new_text, "Another window became active.")
            clipboard.set_text(new_text, transient=True)
            our_seq = clipboard.sequence_number()
            keyboard_sim.send_paste()
            # Apps read the clipboard asynchronously after Ctrl+V; wait before restoring.
            time.sleep(restore_delay_ms / 1000.0)
            if snap is not None and clipboard.sequence_number() == our_seq:
                clipboard.restore(snap)
            snap = None
        except clipboard.ClipboardError as exc:
            return ReplaceResult(ReplaceOutcome.FAILED, f"Clipboard error: {exc}")
        except OSError as exc:
            log.warning("Paste input failed: %s", exc)
            return _fallback(new_text, f"Couldn't send the paste command to {target.app_label}.")
        finally:
            if snap is not None:
                try:
                    clipboard.restore(snap)
                except clipboard.ClipboardError:
                    pass
    return ReplaceResult(ReplaceOutcome.REPLACED, f"Replaced the text in {target.app_label}.")
