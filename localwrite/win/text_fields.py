"""Read-only access to standard Win32 edit controls for the optional real-time assistant.

Safety rules (enforced here, not in the UI):
- Only classic Edit / RichEdit controls are supported (they answer WM_GETTEXT).
- Password fields (ES_PASSWORD) and read-only fields are never read.
- Excluded applications and windows whose title suggests credentials are skipped.
No keyboard hooks are used; the focused control's text is read on a timer.
"""
from __future__ import annotations

import ctypes
import re
from dataclasses import dataclass
from ctypes import wintypes

from localwrite.win import winapi as w
from localwrite.win.window_info import WindowTarget, class_name, get_foreground_target

SUPPORTED_CLASSES = {
    "edit", "richedit20w", "richedit20a", "richedit50w", "richeditd2dpt", "richedit60w",
    "windowsforms10.edit", "windowsforms10.richedit20w",
}
_SENSITIVE_TITLE = re.compile(r"password|passwort|contrase|passcode|\bpin\b|sign[ -]?in|log[ -]?in|vault|bank|credential", re.I)

MAX_FIELD_CHARS = 4000


@dataclass(frozen=True)
class TextField:
    target: WindowTarget
    hwnd: int
    rect: tuple[int, int, int, int]  # physical screen pixels (l, t, r, b)


def _supported_class(name: str) -> bool:
    low = name.lower()
    return low in SUPPORTED_CLASSES or any(low.startswith(c + ".") for c in SUPPORTED_CLASSES if "." in c)


def focused_text_field(excluded_apps: set[str]) -> TextField | None:
    target = get_foreground_target()
    if target is None or not target.focus_hwnd:
        return None
    return text_field_for(target, target.focus_hwnd, excluded_apps)


def text_field_for(target: WindowTarget, hwnd: int, excluded_apps: set[str]) -> TextField | None:
    """Apply every safety rule to a control; None means 'do not touch'."""
    if target.is_own_process or target.process_name.lower() in excluded_apps:
        return None
    if _SENSITIVE_TITLE.search(target.title or ""):
        return None
    if not _supported_class(class_name(hwnd)):
        return None
    style = w.GetWindowLongW(hwnd, w.GWL_STYLE) & 0xFFFFFFFF
    if style & w.ES_PASSWORD or style & w.ES_READONLY:
        return None
    rc = wintypes.RECT()
    if not w.GetWindowRect(hwnd, ctypes.byref(rc)):
        return None
    return TextField(target, hwnd, (rc.left, rc.top, rc.right, rc.bottom))


def read_field_text(hwnd: int, max_chars: int = MAX_FIELD_CHARS) -> str | None:
    result = w.ULONG_PTR(0)
    ok = w.SendMessageTimeoutW(hwnd, w.WM_GETTEXTLENGTH, 0, 0, w.SMTO_ABORTIFHUNG, 150, ctypes.byref(result))
    if not ok:
        return None
    length = int(result.value)
    if length <= 0:
        return ""
    if length > max_chars:
        return None
    buf = ctypes.create_unicode_buffer(length + 1)
    ok = w.SendMessageTimeoutW(
        hwnd, w.WM_GETTEXT, length + 1, ctypes.addressof(buf), w.SMTO_ABORTIFHUNG, 150, ctypes.byref(result)
    )
    if not ok:
        return None
    return buf.value
