"""UI smoke tests (offscreen): build the controller, pages and popup and drive them."""
import logging
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import QApplication

from localwrite.config.settings import Settings, SettingsStore
from localwrite.core.correction_engine import CorrectionResult
from localwrite.core.diff import change_count, compute_diff
from localwrite.ui.popup import compute_position

SECRET = "my very private sentence about Zanzibar-7731"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def pump(app, seconds=0.3, until=None):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if until and until():
            return True
        time.sleep(0.01)
    return until() if until else True


def test_compute_position_stays_on_screen():
    avail = QRect(0, 0, 1920, 1040)
    size = QSize(600, 400)
    p = compute_position(QPoint(1900, 1000), size, avail, "smart")
    assert p.x() + 600 <= 1920 and p.y() + 400 <= 1040 and p.y() >= 0
    p = compute_position(QPoint(100, 100), size, avail, "cursor")
    assert p.y() > 100  # below the anchor when there is room
    p = compute_position(QPoint(0, 0), size, avail, "bottom_right")
    assert p.x() == avail.right() - 600 - 12  # QRect.right() is left + width - 1


@pytest.fixture
def controller(app, tmp_path, monkeypatch):
    from localwrite import app_controller as ac

    monkeypatch.setenv("LOCALWRITE_HOME", str(tmp_path))
    store = SettingsStore(tmp_path / "settings.json")
    store.save(Settings(model="fake-model", first_run_complete=True))
    c = ac.AppController(app, store)
    yield c
    c.popup.hide()
    c.main_window.hide()


class FakeEngine:
    model = "fake-model"

    def correct(self, text, mode, custom="", temperature_boost=0.0, on_progress=None, cancel=None):
        if on_progress:
            on_progress("I have")
        time.sleep(0.05)
        return CorrectionResult(text, "I have an apple.", mode, "fake-model", 0.05)


def test_popup_states(app, controller):
    popup = controller.popup
    popup.set_context("grammar", "fake-model", can_replace=True, source_note="notepad")
    popup.show_loading("I has a apple.", "Correcting...")
    popup.show_near(QPoint(200, 200), "smart")
    pump(app, 0.2)
    assert popup.isVisible() and popup.status_row.isVisible()
    assert not popup.accept_btn.isEnabled()
    popup.update_stream("I have")
    ops = compute_diff("I has a apple.", "I have an apple.")
    popup.show_result(ops, change_count(ops))
    assert popup.accept_btn.isEnabled() and popup.copy_btn.isEnabled()
    assert "1 improvement" in popup.changes_chip.text()
    assert popup.model_chip.isHidden()  # the model name is never shown in the popup
    popup.show_error("AI error", "ConnectionError: refused", "Start Ollama")
    assert popup.error_panel.isVisible() and not popup.accept_btn.isEnabled()
    assert popup.error_title.text() == "AI error"
    # Only the short title: no hint, no technical details, no details link.
    assert popup.error_hint.isHidden() and popup.error_detail.isHidden() and popup.details_btn.isHidden()
    popup.set_context("grammar", "m", can_replace=False)
    popup.show_result(ops, 1)
    assert not popup.accept_btn.isVisible()  # clipboard source: no replace target


def test_popup_long_text_scrolls_and_resizes(app, controller):
    popup = controller.popup
    long_text = ("This is a fairly long sentence that keeps going. " * 120).strip()
    popup.set_context("grammar", "m", can_replace=True)
    popup.show_loading(long_text, "Working")
    popup.show_near(QPoint(100, 100), "smart")
    pump(app, 0.2)
    avail = popup.screen().availableGeometry()
    assert popup.height() <= avail.height()  # capped; the text scrolls inside
    popup.enter_manual_size()
    popup.resize(900, 700)
    pump(app, 0.1)
    assert popup.width() == 900 and popup.original_view.maximumHeight() > 1000


def test_pages_build_and_navigate(app, controller):
    mw = controller.main_window
    assert mw.PAGES == ("home", "assistant", "settings", "about")
    for key in mw.PAGES:
        mw.show_page(key)
        pump(app, 0.05)
        assert mw.stack.currentWidget() is mw.pages[key]
    page = mw.pages["settings"]
    s = page.collect()
    assert s.model == "fake-model"
    controller.apply_settings(s.copy(default_mode="casual"))
    assert controller.settings.default_mode == "casual"
    assert mw.pages["home"].tiles["casual"].property("selected") is True


def test_full_session_stores_nothing(app, controller, monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(controller, "make_engine", lambda *a, **k: FakeEngine())
    controller.start_session(SECRET, "grammar", None, "clipboard", anchor=QPoint(300, 300))
    assert pump(app, 3, until=lambda: controller._session and controller._session.result is not None)
    assert controller.popup.copy_btn.isEnabled()
    controller.retry_correction()
    assert pump(app, 3, until=lambda: controller._session.result is not None)
    controller.change_mode("professional")
    assert controller._session.mode_key == "professional"
    assert pump(app, 3, until=lambda: controller._session.result is not None)
    controller.close_popup()
    assert controller._session is None  # text discarded with the session
    # Privacy: the text never reaches a log record or any file in the data folder.
    assert SECRET not in caplog.text
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert SECRET.encode() not in f.read_bytes(), f
    assert not list(tmp_path.rglob("*.db"))


def test_assistant_page_correct_and_cancel(app, controller, monkeypatch):
    monkeypatch.setattr(controller, "make_engine", lambda *a, **k: FakeEngine())
    page = controller.main_window.pages["assistant"]
    page.editor.setPlainText("I has a apple.")
    page._run()
    assert pump(app, 3, until=lambda: page._result is not None)
    assert page.copy_btn.isEnabled()
    assert "improvement" in page.result_chip.text()
    page._use()
    assert page.editor.toPlainText() == "I have an apple."
    page._clear()
    assert page.editor.toPlainText() == ""


def test_missing_model_shows_friendly_error(app, controller):
    controller.apply_settings(controller.settings.copy(model=""))
    controller.start_session("teh", "spelling", None, "clipboard", anchor=QPoint(10, 10))
    pump(app, 0.1)
    assert controller.popup.error_panel.isVisible()
    assert controller.popup.error_title.text() == "AI error"


def test_engine_failure_shows_only_ai_error(app, controller, monkeypatch):
    from localwrite.core.ollama_client import OllamaConnectionError

    class FailingEngine:
        model = "fake-model"

        def correct(self, *a, **k):
            raise OllamaConnectionError("Can't reach Ollama", "No server at http://127.0.0.1:11434", "Start Ollama")

    monkeypatch.setattr(controller, "make_engine", lambda *a, **k: FailingEngine())
    controller.start_session("teh text", "spelling", None, "clipboard", anchor=QPoint(10, 10))
    assert pump(app, 3, until=lambda: controller.popup.error_panel.isVisible())
    popup = controller.popup
    assert popup.error_title.text() == "AI error"
    assert popup.error_hint.isHidden() and popup.error_detail.isHidden() and popup.details_btn.isHidden()
    assert popup.retry_btn.isEnabled()


def test_icons_render(app, tmp_path):
    from localwrite.ui.icons import line_icon, render_app_icon, write_ico

    assert not render_app_icon(64, "disabled", live_dot=True).isNull()
    for name in ("home", "pen", "settings", "info", "shield", "server", "chip", "keyboard", "sparkle"):
        assert not line_icon(name).isNull()
    out = tmp_path / "a.ico"
    write_ico(str(out))
    assert out.read_bytes()[:4] == b"\x00\x00\x01\x00"
