"""A native Win32 EDIT control inside a normal top-level window (like classic Notepad).

Usage: native_edit_app.py <text> [password]
Prints the HWND of the edit control.
"""
import ctypes
import sys
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p,
]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetFocus.argtypes = [wintypes.HWND]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_VISIBLE = 0x10000000
WS_CHILD = 0x40000000
WS_BORDER = 0x00800000
ES_MULTILINE = 0x0004
ES_PASSWORD = 0x0020
ES_AUTOVSCROLL = 0x0040
WM_TIMER = 0x0113


def main() -> int:
    text = sys.argv[1]
    password = len(sys.argv) > 2 and sys.argv[2] == "password"
    frame = user32.CreateWindowExW(
        0, "#32770", "LocalWrite native edit test", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        200, 200, 520, 240, None, None, None, None,
    )
    style = WS_CHILD | WS_VISIBLE | WS_BORDER | (ES_PASSWORD if password else ES_MULTILINE | ES_AUTOVSCROLL)
    edit = user32.CreateWindowExW(0, "EDIT", text, style, 10, 10, 480, 160, frame, None, None, None)
    kernel32 = ctypes.WinDLL("kernel32")
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]

    def claim_foreground():
        fg = user32.GetForegroundWindow()
        if fg == frame:
            return
        fg_tid = user32.GetWindowThreadProcessId(fg, None)
        me = kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(me, fg_tid, True)
        user32.SetForegroundWindow(frame)
        user32.SetFocus(edit)
        user32.AttachThreadInput(me, fg_tid, False)

    claim_foreground()
    user32.SetFocus(edit)
    print(int(edit), int(frame), flush=True)
    user32.SetTimer(None, 1, 60_000, None)  # safety net: quit after 60s
    user32.SetTimer(None, 2, 150, None)     # keep claiming the foreground for the first seconds
    ticks = 0
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        if msg.message == WM_TIMER and not msg.hWnd:
            if msg.wParam == 2:
                ticks += 1
                if ticks < 20:
                    claim_foreground()
                continue
            break
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
