"""Information about (and control over) the window the user is working in."""
from __future__ import annotations

import ctypes
import os
import time
from dataclasses import dataclass
from ctypes import wintypes

from localwrite.win import winapi as w

# Console-style windows where Ctrl+C means "interrupt", not "copy".
TERMINAL_CLASSES = {
    "consolewindowclass", "cascadia_hosting_window_class", "mintty", "virtualconsoleclass", "putty",
    "puttyconfigbox",
}
TERMINAL_PROCESSES = {
    "windowsterminal.exe", "wt.exe", "conhost.exe", "openconsole.exe", "putty.exe", "kitty.exe",
    "mintty.exe", "alacritty.exe", "wezterm-gui.exe", "conemu64.exe", "conemu.exe", "hyper.exe",
    "tabby.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
}


@dataclass(frozen=True)
class WindowTarget:
    hwnd: int
    pid: int
    thread_id: int
    process_name: str
    title: str
    class_name: str
    focus_hwnd: int = 0
    caret: tuple[int, int] | None = None  # physical screen pixels

    @property
    def app_label(self) -> str:
        name = self.process_name[:-4] if self.process_name.lower().endswith(".exe") else self.process_name
        return name or "the application"

    @property
    def is_own_process(self) -> bool:
        return self.pid == os.getpid()

    @property
    def is_terminal(self) -> bool:
        return self.class_name.lower() in TERMINAL_CLASSES or self.process_name.lower() in TERMINAL_PROCESSES


def _hwnd_int(h) -> int:
    return int(h or 0)


def window_title(hwnd: int) -> str:
    n = w.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    w.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    w.GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_pid_thread(hwnd: int) -> tuple[int, int]:
    pid = wintypes.DWORD(0)
    tid = w.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value), int(tid)


def process_name(pid: int) -> str:
    handle = w.OpenProcess(w.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if w.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return ""
    finally:
        w.CloseHandle(handle)


def gui_thread_info(thread_id: int) -> w.GUITHREADINFO | None:
    info = w.GUITHREADINFO()
    info.cbSize = ctypes.sizeof(w.GUITHREADINFO)
    if not w.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
        return None
    return info


def _caret_position(info: w.GUITHREADINFO | None) -> tuple[int, int] | None:
    if info is None or not info.hwndCaret:
        return None
    rc = info.rcCaret
    if rc.right == 0 and rc.bottom == 0 and rc.left == 0 and rc.top == 0:
        return None
    pt = wintypes.POINT(rc.left, rc.bottom)
    if not w.ClientToScreen(info.hwndCaret, ctypes.byref(pt)):
        return None
    return int(pt.x), int(pt.y)


def get_foreground_target() -> WindowTarget | None:
    hwnd = _hwnd_int(w.GetForegroundWindow())
    if not hwnd:
        return None
    return target_for_window(hwnd)


def target_for_window(hwnd: int) -> WindowTarget:
    root = _hwnd_int(w.GetAncestor(hwnd, w.GA_ROOT)) or hwnd
    pid, tid = window_pid_thread(root)
    info = gui_thread_info(tid)
    focus = _hwnd_int(info.hwndFocus) if info else 0
    return WindowTarget(
        hwnd=root, pid=pid, thread_id=tid, process_name=process_name(pid), title=window_title(root),
        class_name=class_name(root), focus_hwnd=focus, caret=_caret_position(info),
    )


def cursor_position() -> tuple[int, int]:
    pt = wintypes.POINT()
    w.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def is_window_alive(target: WindowTarget) -> bool:
    if not w.IsWindow(target.hwnd):
        return False
    pid, _ = window_pid_thread(target.hwnd)
    return pid == target.pid


def foreground_root() -> int:
    hwnd = _hwnd_int(w.GetForegroundWindow())
    return _hwnd_int(w.GetAncestor(hwnd, w.GA_ROOT)) if hwnd else 0


def focus_window(target: WindowTarget, timeout: float = 0.8) -> bool:
    """Bring the target window back to the foreground; True if it is now active."""
    hwnd = target.hwnd
    if foreground_root() == hwnd:
        return True
    if w.IsIconic(hwnd):
        w.ShowWindow(hwnd, w.SW_RESTORE)
    if not w.SetForegroundWindow(hwnd):
        # Foreground lock: temporarily attach our input queue to the foreground thread.
        fg = _hwnd_int(w.GetForegroundWindow())
        our_tid = w.GetCurrentThreadId()
        fg_tid = window_pid_thread(fg)[1] if fg else 0
        attached = bool(fg_tid and fg_tid != our_tid and w.AttachThreadInput(our_tid, fg_tid, True))
        try:
            w.BringWindowToTop(hwnd)
            w.SetForegroundWindow(hwnd)
        finally:
            if attached:
                w.AttachThreadInput(our_tid, fg_tid, False)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if foreground_root() == hwnd:
            return True
        time.sleep(0.02)
    return foreground_root() == hwnd
