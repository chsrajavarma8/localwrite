"""Desktop integration tests: real windows, real keyboard input, real clipboard.

Run with:  set LOCALWRITE_DESKTOP_TESTS=1 && pytest tests/test_desktop.py
(add LOCALWRITE_OLLAMA_TESTS=1 for the full workflow test through Ollama).
Don't type or click while they run - they move keyboard focus around.
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from localwrite.win import clipboard, keyboard_sim
from localwrite.win import winapi as w
from localwrite.win.hotkeys import HotkeyManager
from localwrite.win.text_capture import CaptureError, capture_selection
from localwrite.win.text_fields import focused_text_field, read_field_text
from localwrite.win.text_replace import ReplaceOutcome, replace_selection
from localwrite.win.window_info import WindowTarget, focus_window, foreground_root, get_foreground_target

HELPERS = Path(__file__).parent / "helpers"
pytestmark = pytest.mark.desktop
SENTINEL = "USER CLIPBOARD SENTINEL ✓"


@pytest.fixture(scope="module", autouse=True)
def preserve_real_clipboard():
    """These tests use the clipboard heavily; give the user's clipboard back afterwards."""
    snap = clipboard.snapshot()
    yield
    clipboard.restore(snap)


def _wait_foreground(hwnd: int, timeout=6.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if foreground_root() == hwnd:
            return True
        time.sleep(0.05)
    return False


def _wait_file(path: Path, expected: str, timeout=3.0) -> str:
    deadline = time.monotonic() + timeout
    content = ""
    while time.monotonic() < deadline:
        content = path.read_text(encoding="utf-8")
        if content == expected:
            break
        time.sleep(0.05)
    return content


def _bring(hwnd: int) -> WindowTarget:
    # Windows may re-activate another window shortly after a previous test window is
    # destroyed, so insist that ours stays in front for a moment.
    dummy = WindowTarget(hwnd, 0, 0, "", "", "")
    for _ in range(5):
        if not _wait_foreground(hwnd, 1.5):
            focus_window(dummy)
        time.sleep(0.4)
        target = get_foreground_target()
        if target and target.hwnd == hwnd:
            return target
    raise AssertionError("test window did not stay in the foreground")


@pytest.fixture
def qt_target(tmp_path):
    src = tmp_path / "in.txt"
    out = tmp_path / "out.txt"
    src.write_text("I has a apple and they was happy.", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(HELPERS / "target_app.py"), str(src), str(out)],
                            stdout=subprocess.PIPE, text=True)
    hwnd = int(proc.stdout.readline().strip())
    from localwrite.win.window_info import _hwnd_int
    root = _hwnd_int(w.GetAncestor(hwnd, w.GA_ROOT)) or hwnd
    yield root, out, proc
    proc.kill()
    proc.wait(5)


def _native_edit(text, password=False):
    args = [sys.executable, str(HELPERS / "native_edit_app.py"), text] + (["password"] if password else [])
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, text=True)
    edit, frame = (int(x) for x in proc.stdout.readline().split())
    return edit, frame, proc


def test_clipboard_snapshot_roundtrip():
    custom = w.RegisterClipboardFormatW("LocalWriteTestFormat")
    clipboard._set_formats([(w.CF_UNICODETEXT, (SENTINEL + "\0").encode("utf-16-le")), (custom, b"\x01\x02\x03")])
    snap = clipboard.snapshot()
    clipboard.set_text("temporary", transient=True)
    assert clipboard.get_text() == "temporary"
    clipboard.restore(snap)
    assert clipboard.get_text() == SENTINEL
    assert w.IsClipboardFormatAvailable(custom)


def test_hotkey_fires_on_real_key_press():
    got = threading.Event()
    mgr = HotkeyManager(lambda action: got.set() if action == "test" else None)
    mgr.start()
    try:
        res = mgr.set_hotkeys({"test": "Ctrl+Alt+Shift+F24"})
        assert res == {"test": None}
        keyboard_sim.send_combo(w.VK_CONTROL, w.VK_MENU, w.VK_SHIFT, 0x87)
        assert got.wait(2), "WM_HOTKEY was not delivered"
        # Temporary hotkeys survive set_hotkeys and can be removed
        assert mgr.register_temporary("esc", "Escape") is None
        mgr.set_hotkeys({"test": "Ctrl+Alt+Shift+F23"})
        assert "esc" in mgr.registered()
        mgr.unregister("esc")
        assert "esc" not in mgr.registered()
    finally:
        mgr.stop()


def test_capture_and_replace_roundtrip(qt_target):
    hwnd, out, _ = qt_target
    clipboard.set_text(SENTINEL)
    target = _bring(hwnd)

    res = capture_selection(restore_clipboard=True, target=target)
    assert res.text == "I has a apple and they was happy."
    assert clipboard.get_text() == SENTINEL, "clipboard must be restored after capture"

    rr = replace_selection(target, res.text, "I have an apple and they were happy.", restore_delay_ms=400)
    assert rr.outcome is ReplaceOutcome.REPLACED, rr.message
    assert _wait_file(out, "I have an apple and they were happy.") == "I have an apple and they were happy."
    assert clipboard.get_text() == SENTINEL, "clipboard must be restored after replace"


def test_replace_refuses_when_selection_changed(qt_target):
    hwnd, out, _ = qt_target
    target = _bring(hwnd)
    # Press End to clear the selection, simulating the user clicking elsewhere in the document.
    keyboard_sim.send_combo(0x23)
    time.sleep(0.2)
    rr = replace_selection(target, "I has a apple and they was happy.", "SHOULD NOT BE PASTED")
    assert rr.outcome is ReplaceOutcome.COPIED
    assert out.read_text(encoding="utf-8") == "I has a apple and they was happy."
    assert clipboard.get_text() == "SHOULD NOT BE PASTED"  # fallback leaves text for the user


def test_replace_refuses_closed_window(qt_target):
    hwnd, out, proc = qt_target
    target = _bring(hwnd)
    proc.kill()
    proc.wait(5)
    rr = replace_selection(target, "x", "fallback text")
    assert rr.outcome is ReplaceOutcome.COPIED
    assert clipboard.get_text() == "fallback text"


def test_capture_without_selection_reports_error(qt_target):
    hwnd, _, _ = qt_target
    target = _bring(hwnd)
    keyboard_sim.send_combo(0x23)  # End: no selection
    time.sleep(0.2)
    with pytest.raises(CaptureError) as ei:
        capture_selection(target=target, timeout_ms=500)
    assert "No text selected" in ei.value.title


def test_realtime_reads_native_edit_but_never_password_fields():
    from localwrite.win.text_fields import text_field_for
    from localwrite.win.window_info import target_for_window

    edit, frame, proc = _native_edit("teh quick brwon fox")
    try:
        target = target_for_window(frame)
        field = text_field_for(target, edit, set())
        assert field is not None and field.hwnd == edit
        assert read_field_text(field.hwnd) == "teh quick brwon fox"
        assert text_field_for(target, edit, {"python.exe"}) is None  # excluded app
        assert text_field_for(target, frame, set()) is None          # not an edit control
    finally:
        proc.kill()
    edit, frame, proc = _native_edit("secret", password=True)
    try:
        target = target_for_window(frame)
        assert text_field_for(target, edit, set()) is None  # ES_PASSWORD fields are never read
    finally:
        proc.kill()


@pytest.mark.ollama
def test_full_workflow_with_ollama(qt_target):
    """Select text in another app -> capture -> Ollama -> replace."""
    from localwrite.config.settings import Settings
    from localwrite.core.correction_engine import CorrectionEngine
    from localwrite.core.ollama_client import OllamaClient

    model = os.environ.get("LOCALWRITE_TEST_MODEL", "llama3.2:3b")
    hwnd, out, _ = qt_target
    target = _bring(hwnd)
    captured = capture_selection(target=target)
    engine = CorrectionEngine(OllamaClient(Settings().ollama_url), model, timeout=180)
    result = engine.correct(captured.text, "grammar")
    assert result.changed
    assert "have" in result.corrected and "were" in result.corrected
    rr = replace_selection(target, captured.text, result.corrected)
    assert rr.outcome is ReplaceOutcome.REPLACED, rr.message
    expected = result.corrected.replace("\r\n", "\n")
    assert _wait_file(out, expected) == expected
