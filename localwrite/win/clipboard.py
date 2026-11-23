"""Windows clipboard access with full snapshot/restore support.

``snapshot()`` copies every memory-backed format on the clipboard (text, HTML,
RTF, images as DIB, file lists, app-specific formats...) so the user's
clipboard can be put back exactly after LocalWrite borrows it.
"""
from __future__ import annotations

import ctypes
import json
import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from localwrite.win import winapi as w

log = logging.getLogger(__name__)

# One lock for every clipboard transaction inside this process.
lock = threading.RLock()

_MAX_SNAPSHOT_BYTES = 128 * 1024 * 1024
# Formats whose handle is a GDI object rather than global memory, plus
# formats Windows synthesizes automatically from CF_UNICODETEXT.
_GDI_FORMATS = {
    w.CF_BITMAP, w.CF_METAFILEPICT, w.CF_PALETTE, w.CF_ENHMETAFILE, w.CF_OWNERDISPLAY,
    w.CF_DSPBITMAP, w.CF_DSPMETAFILEPICT, w.CF_DSPENHMETAFILE,
}
_SYNTHESIZED_TEXT = {w.CF_TEXT, w.CF_OEMTEXT}
_SKIP_NAMED = {"ole private data", "dataobject"}  # in-process OLE pointers, meaningless once copied


class ClipboardError(Exception):
    pass


@dataclass
class ClipboardSnapshot:
    formats: list[tuple[int, bytes]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.formats


def _format_name(fmt: int) -> str:
    if fmt < 0xC000:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    n = w.GetClipboardFormatNameW(fmt, buf, 256)
    return buf.value if n else ""


class _OwnerWindow:
    """A hidden window that owns the clipboard while we write to it."""

    def __enter__(self):
        self.hwnd = w.CreateWindowExW(0, "STATIC", "LocalWriteClipboard", 0, 0, 0, 0, 0, None, None, None, None)
        return self.hwnd

    def __exit__(self, *exc):
        if self.hwnd:
            w.DestroyWindow(self.hwnd)


@contextmanager
def _opened(hwnd=None, timeout: float = 0.8):
    deadline = time.monotonic() + timeout
    while not w.OpenClipboard(hwnd):
        if time.monotonic() > deadline:
            raise ClipboardError("The clipboard is in use by another application. Please try again.")
        time.sleep(0.015)
    try:
        yield
    finally:
        w.CloseClipboard()


def sequence_number() -> int:
    return int(w.GetClipboardSequenceNumber())


def _read_hglobal(handle) -> bytes | None:
    size = w.GlobalSize(handle)
    if not size:
        return None
    ptr = w.GlobalLock(handle)
    if not ptr:
        return None
    try:
        return ctypes.string_at(ptr, size)
    finally:
        w.GlobalUnlock(handle)


def _alloc(data: bytes):
    handle = w.GlobalAlloc(w.GMEM_MOVEABLE, max(1, len(data)))
    if not handle:
        raise ClipboardError("Out of memory while preparing clipboard data.")
    ptr = w.GlobalLock(handle)
    if not ptr:
        w.GlobalFree(handle)
        raise ClipboardError("Could not lock clipboard memory.")
    try:
        ctypes.memmove(ptr, data, len(data))
    finally:
        w.GlobalUnlock(handle)
    return handle


def get_text() -> str | None:
    """Return the clipboard's Unicode text, or None if it holds no text."""
    with lock, _opened():
        handle = w.GetClipboardData(w.CF_UNICODETEXT)
        if not handle:
            return None
        raw = _read_hglobal(handle)
    if raw is None:
        return None
    text = raw.decode("utf-16-le", errors="replace")
    nul = text.find("\x00")
    return text if nul < 0 else text[:nul]


def _set_formats(items: list[tuple[int, bytes]]) -> None:
    with lock, _OwnerWindow() as hwnd, _opened(hwnd):
        if not w.EmptyClipboard():
            raise ClipboardError("Could not clear the clipboard.")
        for fmt, data in items:
            handle = _alloc(data)
            if not w.SetClipboardData(fmt, handle):
                w.GlobalFree(handle)
                log.debug("SetClipboardData failed for format %s (err %s)", fmt, w.last_error())


def _private_markers() -> list[tuple[int, bytes]]:
    """Formats asking Windows clipboard history / cloud sync / monitors to ignore this content."""
    zero = (0).to_bytes(4, "little")
    out = []
    for name, data in (
        ("ExcludeClipboardContentFromMonitorProcessing", zero),
        ("CanIncludeInClipboardHistory", zero),
        ("CanUploadToCloudClipboard", zero),
    ):
        fmt = w.RegisterClipboardFormatW(name)
        if fmt:
            out.append((fmt, data))
    return out


def set_text(text: str, transient: bool = False) -> None:
    """Put text on the clipboard.

    transient=True marks it as excluded from Win+V history and cloud clipboard,
    used for the short-lived copies LocalWrite makes while pasting.
    """
    items = [(w.CF_UNICODETEXT, (text + "\x00").encode("utf-16-le"))]
    if transient:
        items += _private_markers()
    _set_formats(items)


def snapshot() -> ClipboardSnapshot:
    snap = ClipboardSnapshot()
    total = 0
    with lock, _opened():
        fmt = 0
        available: list[int] = []
        while True:
            fmt = w.EnumClipboardFormats(fmt)
            if not fmt:
                break
            available.append(fmt)
        has_unicode = w.CF_UNICODETEXT in available
        for fmt in available:
            if fmt in _GDI_FORMATS or (w.CF_PRIVATEFIRST <= fmt <= w.CF_GDIOBJLAST):
                continue
            if has_unicode and fmt in _SYNTHESIZED_TEXT:
                continue
            if _format_name(fmt).lower() in _SKIP_NAMED:
                continue
            handle = w.GetClipboardData(fmt)
            if not handle:
                continue
            data = _read_hglobal(handle)
            if data is None:
                continue
            total += len(data)
            if total > _MAX_SNAPSHOT_BYTES:
                log.warning("Clipboard snapshot too large; some formats will not be restored")
                break
            snap.formats.append((fmt, data))
    return snap


def restore(snap: ClipboardSnapshot) -> None:
    _set_formats(list(snap.formats))


def wait_for_change(previous_seq: int, timeout_ms: int) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        if sequence_number() != previous_seq:
            return True
        time.sleep(0.01)
    return sequence_number() != previous_seq


def get_text_with_retry(timeout_ms: int = 250) -> str | None:
    """Some apps empty the clipboard first and render text a moment later."""
    deadline = time.monotonic() + timeout_ms / 1000.0
    while True:
        try:
            text = get_text()
        except ClipboardError:
            text = None
        if text is not None or time.monotonic() > deadline:
            return text
        time.sleep(0.02)


def is_vscode_empty_selection_copy() -> bool:
    """VS Code copies the whole current line when nothing is selected; detect that."""
    fmt = w.RegisterClipboardFormatW("vscode-editor-data")
    if not fmt or not w.IsClipboardFormatAvailable(fmt):
        return False
    try:
        with lock, _opened():
            handle = w.GetClipboardData(fmt)
            raw = _read_hglobal(handle) if handle else None
        if not raw:
            return False
        text = raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        data = json.loads(text)
        return bool(data.get("isFromEmptySelection"))
    except (ClipboardError, ValueError):
        return False
