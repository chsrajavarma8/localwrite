"""End-to-end through the real application: hotkey -> capture -> Ollama -> popup -> Accept -> replaced.

Needs an unlocked desktop and a running Ollama with a model:
    set LOCALWRITE_DESKTOP_TESTS=1 && set LOCALWRITE_OLLAMA_TESTS=1 && pytest tests/test_e2e_app.py
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.desktop, pytest.mark.ollama]

HELPERS = Path(__file__).parent / "helpers"


def test_hotkey_to_replacement(tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from localwrite import app_controller as ac
    from localwrite.config.settings import Settings, SettingsStore
    from localwrite.win import clipboard, keyboard_sim
    from localwrite.win import winapi as w
    from localwrite.win.window_info import WindowTarget, _hwnd_int, focus_window, get_foreground_target

    model = os.environ.get("LOCALWRITE_TEST_MODEL", "llama3.2:3b")
    app = QApplication.instance() or QApplication([])
    store = SettingsStore(tmp_path / "settings.json")
    store.save(Settings(model=model, first_run_complete=True, show_notifications=False, timeout_seconds=180))
    monkeypatch.setenv("LOCALWRITE_HOME", str(tmp_path))
    controller = ac.AppController(app, store, start_minimized=True)
    controller.start()

    def pump(seconds, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            if until and until():
                return True
            time.sleep(0.01)
        return bool(until and until())

    user_clip = clipboard.snapshot()
    src, out = tmp_path / "in.txt", tmp_path / "out.txt"
    original = "She dont like going to school becuase it are boring."
    src.write_text(original, encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(HELPERS / "target_app.py"), str(src), str(out)],
                            stdout=subprocess.PIPE, text=True)
    try:
        hwnd = int(proc.stdout.readline())
        root = _hwnd_int(w.GetAncestor(hwnd, w.GA_ROOT)) or hwnd
        for _ in range(30):
            t = get_foreground_target()
            if t and t.hwnd == root:
                break
            focus_window(WindowTarget(root, 0, 0, "", "", ""))
            pump(0.2)
        clipboard.set_text("CLIPBOARD BEFORE")

        # The real global shortcut, delivered through RegisterHotKey.
        keyboard_sim.send_combo(w.VK_CONTROL, w.VK_MENU, ord("G"))
        assert pump(10, until=lambda: controller._session is not None), "hotkey did not start a session"
        session = controller._session
        assert session.original == original
        assert session.target.hwnd == root
        assert controller.popup.isVisible()
        assert pump(180, until=lambda: session.result is not None or controller.popup.error_panel.isVisible())
        assert session.result is not None, controller.popup.error_title.text()
        assert controller.popup.accept_btn.isEnabled()
        corrected = session.result.corrected

        QTest.mouseClick(controller.popup.accept_btn, Qt.MouseButton.LeftButton)
        assert pump(10, until=lambda: not controller.popup.isVisible()), controller.popup.info_label.text()
        assert pump(3, until=lambda: out.read_text(encoding="utf-8") == corrected.replace("\r\n", "\n"))
        assert clipboard.get_text() == "CLIPBOARD BEFORE"
        assert not list(tmp_path.rglob("*.db"))  # nothing stored
    finally:
        proc.kill()
        controller.shutdown()
        clipboard.restore(user_clip)
