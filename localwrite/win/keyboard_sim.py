"""Synthetic keyboard input (only ever Ctrl+C / Ctrl+V on explicit user action)."""
from __future__ import annotations

import ctypes
import time

from localwrite.win import winapi as w

# Marker placed in dwExtraInfo so our own synthetic events are identifiable.
LOCALWRITE_INPUT_MARKER = 0x4C57_5254

_EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, w.VK_RCONTROL, w.VK_RMENU}
_MODIFIERS = (
    w.VK_LCONTROL, w.VK_RCONTROL, w.VK_LMENU, w.VK_RMENU, w.VK_LSHIFT, w.VK_RSHIFT, w.VK_LWIN, w.VK_RWIN,
)


def _key_input(vk: int, up: bool) -> w.INPUT:
    flags = w.KEYEVENTF_KEYUP if up else 0
    if vk in _EXTENDED:
        flags |= w.KEYEVENTF_EXTENDEDKEY
    inp = w.INPUT()
    inp.type = w.INPUT_KEYBOARD
    inp.ki = w.KEYBDINPUT(vk, w.MapVirtualKeyW(vk, 0), flags, 0, LOCALWRITE_INPUT_MARKER)
    return inp


def send_key_events(events: list[tuple[int, bool]]) -> None:
    arr = (w.INPUT * len(events))(*[_key_input(vk, up) for vk, up in events])
    sent = w.SendInput(len(events), arr, ctypes.sizeof(w.INPUT))
    if sent != len(events):
        raise OSError(f"SendInput delivered {sent}/{len(events)} events (error {w.last_error()})")


def send_combo(*vks: int) -> None:
    """Press keys in order and release them in reverse, e.g. send_combo(VK_CONTROL, ord('C'))."""
    events = [(vk, False) for vk in vks] + [(vk, True) for vk in reversed(vks)]
    send_key_events(events)


def send_copy() -> None:
    send_combo(w.VK_CONTROL, ord("C"))


def send_paste() -> None:
    send_combo(w.VK_CONTROL, ord("V"))


def pressed_modifiers() -> list[int]:
    return [vk for vk in _MODIFIERS if w.GetAsyncKeyState(vk) & 0x8000]


def wait_for_modifiers_released(timeout: float = 1.5) -> bool:
    """Wait until the user lets go of Ctrl/Alt/Shift/Win from the hotkey.

    Sending Ctrl+C while Alt is still physically down would arrive as Ctrl+Alt+C.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pressed_modifiers():
            return True
        time.sleep(0.01)
    return not pressed_modifiers()


def release_stuck_modifiers() -> None:
    held = pressed_modifiers()
    if held:
        send_key_events([(vk, True) for vk in held])
