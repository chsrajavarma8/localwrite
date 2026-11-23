"""ctypes bindings for the Win32 functions LocalWrite needs.

Every function gets explicit argtypes/restype so 64-bit handles are never
truncated to 32-bit ints (the ctypes default).
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

if sys.platform != "win32":  # pragma: no cover - the app is Windows-only
    raise ImportError("localwrite.win requires Windows")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t
LPARAM = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t

# ---------------------------------------------------------------- constants
CF_TEXT = 1
CF_BITMAP = 2
CF_METAFILEPICT = 3
CF_OEMTEXT = 7
CF_DIB = 8
CF_PALETTE = 9
CF_UNICODETEXT = 13
CF_ENHMETAFILE = 14
CF_HDROP = 15
CF_LOCALE = 16
CF_DIBV5 = 17
CF_OWNERDISPLAY = 0x0080
CF_DSPTEXT = 0x0081
CF_DSPBITMAP = 0x0082
CF_DSPMETAFILEPICT = 0x0083
CF_DSPENHMETAFILE = 0x008E
CF_PRIVATEFIRST = 0x0200
CF_GDIOBJLAST = 0x03FF

GMEM_MOVEABLE = 0x0002

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_LSHIFT, VK_RSHIFT, VK_LCONTROL, VK_RCONTROL, VK_LMENU, VK_RMENU = 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_NULL = 0x0000
WM_QUIT = 0x0012
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
WM_HOTKEY = 0x0312
WM_USER = 0x0400
WM_APP = 0x8000
EM_GETSEL = 0x00B0
EM_SETSEL = 0x00B1

PM_NOREMOVE = 0x0000
SMTO_ABORTIFHUNG = 0x0002
SMTO_BLOCK = 0x0001

SW_RESTORE = 9
GA_ROOT = 2
GWL_STYLE = -16
ES_PASSWORD = 0x0020
ES_READONLY = 0x0800

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

ERROR_HOTKEY_ALREADY_REGISTERED = 1409


# ---------------------------------------------------------------- structures
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


MSG = wintypes.MSG


def _fn(dll, name, restype, *argtypes):
    f = getattr(dll, name)
    f.restype = restype
    f.argtypes = list(argtypes)
    return f


H = wintypes.HANDLE
HWND = wintypes.HWND
UINT = wintypes.UINT
BOOL = wintypes.BOOL
DWORD = wintypes.DWORD

# clipboard
OpenClipboard = _fn(user32, "OpenClipboard", BOOL, HWND)
CloseClipboard = _fn(user32, "CloseClipboard", BOOL)
EmptyClipboard = _fn(user32, "EmptyClipboard", BOOL)
GetClipboardData = _fn(user32, "GetClipboardData", H, UINT)
SetClipboardData = _fn(user32, "SetClipboardData", H, UINT, H)
EnumClipboardFormats = _fn(user32, "EnumClipboardFormats", UINT, UINT)
GetClipboardSequenceNumber = _fn(user32, "GetClipboardSequenceNumber", DWORD)
RegisterClipboardFormatW = _fn(user32, "RegisterClipboardFormatW", UINT, wintypes.LPCWSTR)
GetClipboardFormatNameW = _fn(user32, "GetClipboardFormatNameW", ctypes.c_int, UINT, wintypes.LPWSTR, ctypes.c_int)
IsClipboardFormatAvailable = _fn(user32, "IsClipboardFormatAvailable", BOOL, UINT)

GlobalAlloc = _fn(kernel32, "GlobalAlloc", H, UINT, ctypes.c_size_t)
GlobalLock = _fn(kernel32, "GlobalLock", ctypes.c_void_p, H)
GlobalUnlock = _fn(kernel32, "GlobalUnlock", BOOL, H)
GlobalSize = _fn(kernel32, "GlobalSize", ctypes.c_size_t, H)
GlobalFree = _fn(kernel32, "GlobalFree", H, H)

# windows
CreateWindowExW = _fn(
    user32, "CreateWindowExW", HWND, DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, HWND, wintypes.HMENU, wintypes.HINSTANCE,
    ctypes.c_void_p,
)
DestroyWindow = _fn(user32, "DestroyWindow", BOOL, HWND)
GetForegroundWindow = _fn(user32, "GetForegroundWindow", HWND)
SetForegroundWindow = _fn(user32, "SetForegroundWindow", BOOL, HWND)
BringWindowToTop = _fn(user32, "BringWindowToTop", BOOL, HWND)
ShowWindow = _fn(user32, "ShowWindow", BOOL, HWND, ctypes.c_int)
IsIconic = _fn(user32, "IsIconic", BOOL, HWND)
IsWindow = _fn(user32, "IsWindow", BOOL, HWND)
IsWindowVisible = _fn(user32, "IsWindowVisible", BOOL, HWND)
GetWindowThreadProcessId = _fn(user32, "GetWindowThreadProcessId", DWORD, HWND, ctypes.POINTER(DWORD))
GetWindowTextLengthW = _fn(user32, "GetWindowTextLengthW", ctypes.c_int, HWND)
GetWindowTextW = _fn(user32, "GetWindowTextW", ctypes.c_int, HWND, wintypes.LPWSTR, ctypes.c_int)
GetClassNameW = _fn(user32, "GetClassNameW", ctypes.c_int, HWND, wintypes.LPWSTR, ctypes.c_int)
GetGUIThreadInfo = _fn(user32, "GetGUIThreadInfo", BOOL, DWORD, ctypes.POINTER(GUITHREADINFO))
GetAncestor = _fn(user32, "GetAncestor", HWND, HWND, UINT)
AttachThreadInput = _fn(user32, "AttachThreadInput", BOOL, DWORD, DWORD, BOOL)
GetWindowRect = _fn(user32, "GetWindowRect", BOOL, HWND, ctypes.POINTER(wintypes.RECT))
ClientToScreen = _fn(user32, "ClientToScreen", BOOL, HWND, ctypes.POINTER(wintypes.POINT))
GetCursorPos = _fn(user32, "GetCursorPos", BOOL, ctypes.POINTER(wintypes.POINT))
GetWindowLongW = _fn(user32, "GetWindowLongW", wintypes.LONG, HWND, ctypes.c_int)
SendMessageTimeoutW = _fn(
    user32, "SendMessageTimeoutW", LRESULT, HWND, UINT, WPARAM, LPARAM, UINT, UINT, ctypes.POINTER(ULONG_PTR)
)

# input
GetAsyncKeyState = _fn(user32, "GetAsyncKeyState", ctypes.c_short, ctypes.c_int)
SendInput = _fn(user32, "SendInput", UINT, UINT, ctypes.POINTER(INPUT), ctypes.c_int)
MapVirtualKeyW = _fn(user32, "MapVirtualKeyW", UINT, UINT, UINT)

# hotkeys / messages
RegisterHotKey = _fn(user32, "RegisterHotKey", BOOL, HWND, ctypes.c_int, UINT, UINT)
UnregisterHotKey = _fn(user32, "UnregisterHotKey", BOOL, HWND, ctypes.c_int)
GetMessageW = _fn(user32, "GetMessageW", BOOL, ctypes.POINTER(MSG), HWND, UINT, UINT)
PeekMessageW = _fn(user32, "PeekMessageW", BOOL, ctypes.POINTER(MSG), HWND, UINT, UINT, UINT)
PostThreadMessageW = _fn(user32, "PostThreadMessageW", BOOL, DWORD, UINT, WPARAM, LPARAM)

# process
GetCurrentThreadId = _fn(kernel32, "GetCurrentThreadId", DWORD)
GetCurrentProcessId = _fn(kernel32, "GetCurrentProcessId", DWORD)
OpenProcess = _fn(kernel32, "OpenProcess", H, DWORD, BOOL, DWORD)
QueryFullProcessImageNameW = _fn(
    kernel32, "QueryFullProcessImageNameW", BOOL, H, DWORD, wintypes.LPWSTR, ctypes.POINTER(DWORD)
)
CloseHandle = _fn(kernel32, "CloseHandle", BOOL, H)


def last_error() -> int:
    return ctypes.get_last_error()
