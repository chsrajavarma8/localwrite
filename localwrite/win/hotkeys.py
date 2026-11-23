"""System-wide hotkeys via the Win32 RegisterHotKey API.

RegisterHotKey only notifies us when the exact registered combination is
pressed - no keyboard hook, no keystroke monitoring. Registrations belong to
the thread that made them, so a dedicated thread owns them and runs a message
loop; other threads send it commands via PostThreadMessage.
"""
from __future__ import annotations

import ctypes
import logging
import queue
import threading
from concurrent.futures import Future
from typing import Callable

from localwrite.win import winapi as w

log = logging.getLogger(__name__)

_WM_COMMAND = w.WM_APP + 0x11


class HotkeyParseError(ValueError):
    pass


_MOD_NAMES = {
    "ctrl": w.MOD_CONTROL, "control": w.MOD_CONTROL,
    "alt": w.MOD_ALT,
    "shift": w.MOD_SHIFT,
    "win": w.MOD_WIN, "meta": w.MOD_WIN, "super": w.MOD_WIN, "windows": w.MOD_WIN,
}
_MOD_ORDER = [(w.MOD_CONTROL, "Ctrl"), (w.MOD_ALT, "Alt"), (w.MOD_SHIFT, "Shift"), (w.MOD_WIN, "Win")]

_KEY_NAMES: dict[str, int] = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "backspace": 0x08, "insert": 0x2D, "ins": 0x2D, "delete": 0x2E, "del": 0x2E, "home": 0x24,
    "end": 0x23, "pgup": 0x21, "pageup": 0x21, "pgdown": 0x22, "pagedown": 0x22, "left": 0x25,
    "up": 0x26, "right": 0x27, "down": 0x28, "pause": 0x13, "print": 0x2C, "printscreen": 0x2C,
    ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF, "`": 0xC0,
    "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
}
_VK_TO_NAME = {
    0x20: "Space", 0x0D: "Enter", 0x09: "Tab", 0x1B: "Escape", 0x08: "Backspace", 0x2D: "Insert",
    0x2E: "Delete", 0x24: "Home", 0x23: "End", 0x21: "PgUp", 0x22: "PgDown", 0x25: "Left", 0x26: "Up",
    0x27: "Right", 0x28: "Down", 0x13: "Pause", 0x2C: "Print",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`", 0xDB: "[",
    0xDC: "\\", 0xDD: "]", 0xDE: "'",
}
for _i in range(1, 25):
    _KEY_NAMES[f"f{_i}"] = 0x6F + _i
    _VK_TO_NAME[0x6F + _i] = f"F{_i}"


def parse_hotkey(text: str) -> tuple[int, int]:
    """Parse 'Ctrl+Alt+G' into (modifiers, virtual key)."""
    if not text or not text.strip():
        raise HotkeyParseError("Shortcut is empty")
    raw = text.strip()
    parts: list[str] = []
    # split on '+' but allow '+' itself as the final key ("Ctrl++")
    token = ""
    for ch in raw:
        if ch == "+" and token:
            parts.append(token.strip())
            token = ""
        else:
            token += ch
    if token:
        parts.append(token.strip())
    mods = 0
    key: int | None = None
    for i, part in enumerate(parts):
        low = part.lower()
        if low in _MOD_NAMES and i < len(parts) - 1:
            mods |= _MOD_NAMES[low]
            continue
        if i != len(parts) - 1:
            raise HotkeyParseError(f"'{part}' is not a modifier key")
        if low in _KEY_NAMES:
            key = _KEY_NAMES[low]
        elif len(part) == 1 and part.isalnum() and part.isascii():
            key = ord(part.upper())
        elif low == "+":
            key = 0xBB
        else:
            raise HotkeyParseError(f"Unknown key '{part}'")
    if key is None:
        raise HotkeyParseError("Shortcut needs a key, not only modifiers")
    return mods, key


def format_hotkey(mods: int, vk: int) -> str:
    names = [name for bit, name in _MOD_ORDER if mods & bit]
    if vk in _VK_TO_NAME:
        names.append(_VK_TO_NAME[vk])
    elif 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        names.append(chr(vk))
    else:
        names.append(f"0x{vk:02X}")
    return "+".join(names)


def normalize_hotkey(text: str) -> str:
    return format_hotkey(*parse_hotkey(text))


def validate_global_hotkey(text: str, allow_bare: bool = False) -> str | None:
    """Return an error message, or None when the shortcut is acceptable."""
    try:
        mods, vk = parse_hotkey(text)
    except HotkeyParseError as exc:
        return str(exc)
    if not allow_bare and not (mods & (w.MOD_CONTROL | w.MOD_ALT | w.MOD_WIN)) and not (0x7C <= vk <= 0x87):
        return "Use at least Ctrl, Alt or Win with the key so normal typing is not affected"
    if mods == (w.MOD_CONTROL | w.MOD_ALT) and vk == 0x2E:
        return "Ctrl+Alt+Delete is reserved by Windows"
    if mods == w.MOD_WIN and vk == ord("L"):
        return "Win+L is reserved by Windows"
    if mods == w.MOD_CONTROL and vk in (ord("C"), ord("V"), ord("X"), ord("Z"), ord("A"), ord("S")):
        return f"{format_hotkey(mods, vk)} is a standard editing shortcut; choose another"
    return None


class HotkeyManager:
    """Owns the hotkey thread. ``callback(action)`` runs on that thread."""

    def __init__(self, callback: Callable[[str], None]) -> None:
        self._callback = callback
        self._commands: "queue.Queue[tuple[str, tuple, Future]]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._ids: dict[str, int] = {}      # action -> registration id
        self._combo: dict[str, str] = {}   # action -> normalized combo
        self._temporary: set[str] = set()
        self._next_id = 1

    # ---------------------------------------------------------------- public API
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="LocalWriteHotkeys", daemon=True)
        self._thread.start()
        if not self._ready.wait(3):
            raise RuntimeError("Hotkey thread failed to start")

    def stop(self) -> None:
        if not self._thread or not self._thread.is_alive():
            return
        w.PostThreadMessageW(self._thread_id, w.WM_QUIT, 0, 0)
        self._thread.join(2)
        self._thread = None

    def set_hotkeys(self, mapping: dict[str, str]) -> dict[str, str | None]:
        """Replace all permanent hotkeys. Returns {action: error message or None}."""
        return self._call("set", dict(mapping))

    def register_temporary(self, action: str, combo: str) -> str | None:
        return self._call("temp_add", action, combo)

    def unregister(self, action: str) -> None:
        self._call("remove", action)

    def suspend(self) -> None:
        self._call("suspend")

    def resume(self) -> dict[str, str | None]:
        return self._call("resume")

    def registered(self) -> dict[str, str]:
        return dict(self._combo)

    # ---------------------------------------------------------------- thread side
    def _call(self, name: str, *args):
        if not self._thread or not self._thread.is_alive():
            raise RuntimeError("Hotkey manager is not running")
        fut: Future = Future()
        self._commands.put((name, args, fut))
        w.PostThreadMessageW(self._thread_id, _WM_COMMAND, 0, 0)
        return fut.result(timeout=3)

    def _run(self) -> None:
        msg = w.MSG()
        # Calling PeekMessage creates this thread's message queue before we report ready.
        w.PeekMessageW(ctypes.byref(msg), None, w.WM_USER, w.WM_USER, w.PM_NOREMOVE)
        self._thread_id = w.GetCurrentThreadId()
        self._ready.set()
        suspended: dict[str, str] = {}
        try:
            while True:
                ret = w.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                if msg.message == w.WM_HOTKEY:
                    action = next((a for a, i in self._ids.items() if i == msg.wParam), None)
                    if action:
                        try:
                            self._callback(action)
                        except Exception:  # noqa: BLE001
                            log.exception("Hotkey callback failed")
                elif msg.message == _WM_COMMAND:
                    while True:
                        try:
                            name, args, fut = self._commands.get_nowait()
                        except queue.Empty:
                            break
                        try:
                            if name == "set":
                                fut.set_result(self._do_set(args[0]))
                            elif name == "temp_add":
                                err = self._do_register(args[0], args[1], allow_bare=True)
                                if err is None:
                                    self._temporary.add(args[0])
                                fut.set_result(err)
                            elif name == "remove":
                                self._do_unregister(args[0])
                                self._temporary.discard(args[0])
                                fut.set_result(None)
                            elif name == "suspend":
                                suspended = {a: c for a, c in self._combo.items() if a not in self._temporary}
                                for a in list(suspended):
                                    self._do_unregister(a)
                                fut.set_result(None)
                            elif name == "resume":
                                results = {a: self._do_register(a, c) for a, c in suspended.items()}
                                suspended = {}
                                fut.set_result(results)
                            else:
                                fut.set_exception(ValueError(name))
                        except Exception as exc:  # noqa: BLE001
                            fut.set_exception(exc)
        finally:
            for action in list(self._ids):
                self._do_unregister(action)

    def _do_set(self, mapping: dict[str, str]) -> dict[str, str | None]:
        for action in [a for a in self._ids if a not in self._temporary]:
            self._do_unregister(action)
        results: dict[str, str | None] = {}
        seen: dict[str, str] = {}
        for action, combo in mapping.items():
            if not combo:
                results[action] = None  # disabled by the user
                continue
            try:
                norm = normalize_hotkey(combo)
            except HotkeyParseError as exc:
                results[action] = str(exc)
                continue
            if norm in seen:
                results[action] = f"Same shortcut as '{seen[norm]}'"
                continue
            seen[norm] = action
            results[action] = self._do_register(action, combo)
        return results

    def _do_register(self, action: str, combo: str, allow_bare: bool = False) -> str | None:
        err = validate_global_hotkey(combo, allow_bare=allow_bare)
        if err:
            return err
        mods, vk = parse_hotkey(combo)
        self._do_unregister(action)
        hid = self._next_id
        self._next_id += 1
        if not w.RegisterHotKey(None, hid, mods | w.MOD_NOREPEAT, vk):
            code = w.last_error()
            if code == w.ERROR_HOTKEY_ALREADY_REGISTERED:
                return f"{format_hotkey(mods, vk)} is already used by another application"
            return f"Windows refused {format_hotkey(mods, vk)} (error {code})"
        self._ids[action] = hid
        self._combo[action] = format_hotkey(mods, vk)
        return None

    def _do_unregister(self, action: str) -> None:
        hid = self._ids.pop(action, None)
        self._combo.pop(action, None)
        if hid is not None:
            w.UnregisterHotKey(None, hid)
