"""AppController: wires hotkeys, text capture, the AI engine, the popup, replacement,
settings, tray and windows together. No user text is ever stored. Lives on the Qt UI thread; all slow
work (clipboard capture, Ollama, replacement) runs on background threads."""
from __future__ import annotations

import dataclasses
import logging
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QInputDialog, QSystemTrayIcon

from localwrite import paths
from localwrite.config.settings import HOTKEY_MODES, Settings, SettingsStore
from localwrite.core.cancel import CancelToken
from localwrite.core.correction_engine import CorrectionEngine, CorrectionResult
from localwrite.core.diff import change_count, compute_diff
from localwrite.core.modes import MODES
from localwrite.core.ollama_client import (
    TROUBLESHOOTING, OllamaCancelledError, OllamaClient, OllamaConnectionError, OllamaError,
)
from localwrite.realtime import RealtimeAssistant
from localwrite.ui import theme
from localwrite.ui.invoker import UiInvoker, run_background
from localwrite.ui.main_window import MainWindow
from localwrite.ui.popup import CorrectionPopup, anchor_for, physical_to_logical
from localwrite.ui.setup_wizard import TEST_SENTENCE, SetupWizard
from localwrite.ui.tray import TrayIcon
from localwrite.win import clipboard, startup
from localwrite.win.hotkeys import HotkeyManager
from localwrite.win.text_capture import CaptureError, capture_selection
from localwrite.win.text_fields import TextField
from localwrite.win.text_replace import ReplaceOutcome, ReplaceResult, replace_selection
from localwrite.win.window_info import WindowTarget, get_foreground_target

log = logging.getLogger(__name__)


@dataclass
class OllamaStatus:
    state: str = "unknown"  # unknown | checking | ok | error
    version: str = ""
    models: list = field(default_factory=list)
    error_title: str = ""
    error_hint: str = ""


@dataclass
class Session:
    id: int
    original: str
    mode_key: str
    target: WindowTarget | None
    source: str  # selection | clipboard | realtime
    custom_instruction: str = ""
    retries: int = 0
    cancel: CancelToken | None = None
    result: CorrectionResult | None = None
    select_all: bool = False


class AppController(QObject):
    status_changed = Signal()
    settings_changed = Signal()

    def __init__(self, app: QApplication, store: SettingsStore, start_minimized: bool = False,
                 force_setup: bool = False) -> None:
        super().__init__()
        self.app = app
        self.store = store
        self.settings: Settings = store.load()
        self.invoker = UiInvoker()
        self.quitting = False
        self.busy = False
        self.ollama_status = OllamaStatus()
        self.hotkey_errors: dict[str, str | None] = {}
        self._suspend_count = 0
        self._session: Session | None = None
        self._session_seq = 0
        self._capturing = False
        self._wizard: SetupWizard | None = None
        self._start_minimized = start_minimized
        self._force_setup = force_setup
        self.apply_theme()

        self.popup = CorrectionPopup()
        self.popup.accept_clicked.connect(self.accept_correction)
        self.popup.copy_clicked.connect(self.copy_correction)
        self.popup.retry_clicked.connect(self.retry_correction)
        self.popup.mode_selected.connect(self.change_mode)
        self.popup.cancel_clicked.connect(self.cancel_correction)
        self.popup.close_clicked.connect(self.close_popup)
        self.popup.visibility_changed.connect(self._popup_visibility)

        self.main_window = MainWindow(self)
        self.tray = TrayIcon(self)
        self.hotkeys = HotkeyManager(lambda action: self.invoker.call(self.on_hotkey, action))
        self.realtime = RealtimeAssistant(self)

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(30_000)
        self._status_timer.timeout.connect(self._periodic)

    # ================================================================== lifecycle
    def start(self) -> None:
        removed = paths.purge_legacy_history()
        if removed:
            log.info("Removed %d correction-history file(s) left by an earlier version", removed)
        self.tray.show()
        try:
            self.hotkeys.start()
        except RuntimeError:
            log.exception("Hotkey thread failed to start")
        errors = self._register_hotkeys()
        failed = {a: e for a, e in errors.items() if e}
        if failed:
            self.notify("Some shortcuts are unavailable",
                        "; ".join(failed.values()) + ". Change them in Settings.", error=True)
        try:
            if startup.is_enabled() != self.settings.start_with_windows:
                startup.set_enabled(self.settings.start_with_windows)
        except OSError:
            log.warning("Could not sync the start-with-Windows registry entry")
        self.realtime.set_enabled(self.settings.realtime_enabled and self.settings.assistant_enabled)
        self.refresh_ollama()
        self._status_timer.start()
        if self._force_setup or not self.settings.first_run_complete:
            self.show_main_window()
            QTimer.singleShot(300, self.run_setup_wizard)
        elif not self._start_minimized or not self.tray_available():
            self.show_main_window()
        else:
            self.notify("LocalWrite is running",
                        f"Select text in any app and press {self.settings.hotkeys.get('general')}.")
        log.info("LocalWrite started (model=%s)", self.settings.model or "-")

    def shutdown(self) -> None:
        self.quitting = True
        self._status_timer.stop()
        self.realtime.set_enabled(False)
        if self._session and self._session.cancel:
            self._session.cancel.cancel()
        self.hotkeys.stop()
        self.tray.hide()
        log.info("LocalWrite stopped")

    def quit(self) -> None:
        self.quitting = True
        self.popup.hide()
        self.app.quit()

    def _periodic(self) -> None:
        self.refresh_ollama(quiet=True)

    # ================================================================== helpers
    def apply_theme(self) -> None:
        theme.apply_light_mode(self.app)
        self.app.setStyleSheet(theme.stylesheet(theme.current()))

    def tray_available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def notify(self, title: str, message: str, error: bool = False, force: bool = False) -> None:
        if (self.settings.show_notifications or error or force) and self.tray_available():
            self.tray.notify(title, message, error)

    def make_engine(self, model: str | None = None, url: str | None = None) -> CorrectionEngine:
        s = self.settings
        return CorrectionEngine(
            OllamaClient(url or s.ollama_url), model if model is not None else s.model,
            temperature=s.temperature, timeout=s.timeout_seconds, keep_alive=s.keep_alive,
            context_length=s.context_length,
        )

    def _set_busy(self, busy: bool) -> None:
        if self.busy != busy:
            self.busy = busy
            self.tray.refresh()

    # ================================================================== settings
    def apply_settings(self, new: Settings) -> dict[str, str | None]:
        old = self.settings
        new = new.validated()
        self.settings = new
        try:
            self.store.save(new)
        except OSError as exc:
            log.error("Saving settings failed: %s", type(exc).__name__)
            self.notify("Settings not saved", f"Couldn't write {self.store.path}", error=True)
        errors = self.hotkey_errors
        if new.hotkeys != old.hotkeys or new.assistant_enabled != old.assistant_enabled:
            errors = self._register_hotkeys()
        if new.start_with_windows != old.start_with_windows:
            try:
                startup.set_enabled(new.start_with_windows)
            except OSError:
                self.notify("Startup setting failed", "Couldn't update the Windows startup entry.", error=True)
        if (new.realtime_enabled, new.assistant_enabled) != (old.realtime_enabled, old.assistant_enabled):
            self.realtime.set_enabled(new.realtime_enabled and new.assistant_enabled)
        if new.ollama_url != old.ollama_url:
            self.refresh_ollama()
        self.settings_changed.emit()
        self.status_changed.emit()
        return errors

    def set_enabled(self, enabled: bool) -> None:
        if enabled == self.settings.assistant_enabled:
            return
        self.apply_settings(self.settings.copy(assistant_enabled=enabled))
        if not enabled:
            self.close_popup()
            self.notify("LocalWrite paused", "Shortcuts are off until you re-enable the assistant.")

    def set_default_mode(self, key: str) -> None:
        if key in MODES and key != self.settings.default_mode:
            self.apply_settings(self.settings.copy(default_mode=key))

    def set_model(self, name: str) -> None:
        if name and name != self.settings.model:
            self.apply_settings(self.settings.copy(model=name))

    def set_realtime_enabled(self, enabled: bool) -> None:
        if enabled != self.settings.realtime_enabled:
            self.apply_settings(self.settings.copy(realtime_enabled=enabled))

    # ================================================================== hotkeys
    def _register_hotkeys(self) -> dict[str, str | None]:
        mapping = {}
        if self.settings.assistant_enabled:
            mapping = {a: c for a, c in self.settings.hotkeys.items() if a != "close_popup"}
        try:
            results = self.hotkeys.set_hotkeys(mapping)
        except RuntimeError:
            results = {a: "Shortcut service is not running" for a in mapping}
        results.setdefault("close_popup", None)
        self.hotkey_errors = results
        for action, err in results.items():
            if err:
                log.warning("Hotkey %s unavailable: %s", action, err)
        return results

    def suspend_hotkeys(self) -> None:
        self._suspend_count += 1
        if self._suspend_count == 1:
            try:
                self.hotkeys.suspend()
            except RuntimeError:
                pass

    def resume_hotkeys(self) -> None:
        if self._suspend_count == 0:
            return
        self._suspend_count -= 1
        if self._suspend_count == 0:
            try:
                self.hotkeys.resume()
            except RuntimeError:
                pass

    def _popup_visibility(self, visible: bool) -> None:
        combo = self.settings.hotkeys.get("close_popup")
        if not combo:
            return
        try:
            if visible:
                self.hotkeys.register_temporary("close_popup", combo)
            else:
                self.hotkeys.unregister("close_popup")
        except RuntimeError:
            pass

    def on_hotkey(self, action: str) -> None:
        if action == "close_popup":
            self.close_popup()
            return
        if not self.settings.assistant_enabled or self._capturing:
            return
        mode = HOTKEY_MODES.get(action) or self.settings.default_mode
        target = get_foreground_target()  # remember the app the user is in right now
        self._capturing = True
        s = self.settings
        run_background(
            self.invoker,
            lambda: capture_selection(restore_clipboard=s.restore_clipboard, timeout_ms=s.copy_timeout_ms, target=target),
            lambda res: self._captured(res, mode),
            lambda exc: self._capture_failed(exc, mode, target),
            name="LocalWriteCapture",
        )

    def _captured(self, res, mode: str) -> None:
        self._capturing = False
        self.start_session(res.text, mode, res.target, "selection")

    def _capture_failed(self, exc: BaseException, mode: str, target: WindowTarget | None) -> None:
        self._capturing = False
        if isinstance(exc, CaptureError):
            title, hint = exc.title, exc.hint
        elif isinstance(exc, clipboard.ClipboardError):
            title, hint = "Clipboard problem", str(exc)
        else:
            log.error("Capture failed", exc_info=exc)
            title, hint = "Couldn't read the selected text", type(exc).__name__
        if target is not None and target.is_own_process and self.main_window.isActiveWindow():
            self.main_window.show_page("assistant")
        self.popup.set_context(mode, self.settings.model, can_replace=False)
        self.popup.show_error(title, "", hint, has_original=False)
        self.popup.show_near(anchor_for(target.caret if target else None, self.settings.popup_position),
                             self.settings.popup_position)

    # ================================================================== sessions
    def _ask_custom_instruction(self) -> str | None:
        text, ok = QInputDialog.getMultiLineText(
            None, "Custom instructions", "What should LocalWrite do with the text?",
            self.settings.custom_instruction or "",
        )
        text = text.strip()
        if not ok or not text:
            return None
        if text != self.settings.custom_instruction:
            self.apply_settings(self.settings.copy(custom_instruction=text))
        return text

    def start_session(self, original: str, mode: str, target: WindowTarget | None, source: str,
                      *, select_all: bool = False, result: CorrectionResult | None = None,
                      anchor=None) -> None:
        if self._session and self._session.cancel:
            self._session.cancel.cancel()
        instruction = self.settings.custom_instruction
        if mode == "custom" and not instruction.strip():
            got = self._ask_custom_instruction()
            if got is None:
                return
            instruction = got
        self._session_seq += 1
        sess = Session(self._session_seq, original, mode, target, source, instruction, select_all=select_all)
        self._session = sess
        note = {"clipboard": "from clipboard", "realtime": "real-time"}.get(source, target.app_label if target else "")
        self.popup.set_context(mode, self.settings.model, can_replace=target is not None, source_note=note)
        if result is not None:
            sess.result = result
            ops = compute_diff(result.original, result.corrected)
            self.popup.show_loading(original, "")
            self.popup.show_result(ops, change_count(ops))
        else:
            self.popup.show_loading(original, "Starting...")
        if anchor is None:
            caret = target.caret if (target and source == "selection") else None
            anchor = anchor_for(caret, self.settings.popup_position)
        self.popup.show_near(anchor, self.settings.popup_position)
        if result is None:
            self._run_correction(sess)

    def _run_correction(self, sess: Session, temperature_boost: float = 0.0) -> None:
        s = self.settings
        if not s.model:
            self.popup.show_error("AI error")
            return
        if sess.cancel:
            sess.cancel.cancel()
        token = CancelToken()
        sess.cancel = token
        sess.result = None
        engine = self.make_engine()
        mode_label = MODES[sess.mode_key].label
        self.popup.show_loading(sess.original, f"{mode_label}...")
        self._set_busy(True)
        last = [0.0]

        def on_progress(partial: str) -> None:  # worker thread
            now = time.monotonic()
            if now - last[0] >= 0.06:
                last[0] = now
                self.invoker.call(self._stream_update, sess.id, token, partial)

        def work():
            return engine.correct(sess.original, sess.mode_key, sess.custom_instruction,
                                  temperature_boost=temperature_boost, on_progress=on_progress, cancel=token)

        run_background(self.invoker, work, lambda r: self._correction_done(sess.id, token, r),
                       lambda e: self._correction_failed(sess.id, token, e), name="LocalWriteCorrection")

    def _current(self, sid: int, token: CancelToken | None = None) -> Session | None:
        """The active session, if it is still the one (and the run) a callback belongs to."""
        sess = self._session
        if not sess or sess.id != sid:
            return None
        if token is not None and (sess.cancel is not token or token.cancelled):
            return None
        return sess

    def _stream_update(self, sid: int, token: CancelToken, partial: str) -> None:
        sess = self._current(sid, token)
        if sess and sess.result is None:
            self.popup.update_stream(partial)

    def _correction_done(self, sid: int, token: CancelToken, result: CorrectionResult) -> None:
        sess = self._current(sid, token)
        if not sess:
            return
        self._set_busy(False)
        sess.result = result
        ops = compute_diff(result.original, result.corrected)
        self.popup.show_result(ops, change_count(ops))
        if self.ollama_status.state != "ok":
            self.refresh_ollama(quiet=True)
        # Nothing is persisted: the text lives only in this session object until the popup closes.

    def _correction_failed(self, sid: int, token: CancelToken, exc: BaseException) -> None:
        sess = self._session
        if not sess or sess.id != sid or sess.cancel is not token:
            return  # superseded by a newer run
        self._set_busy(False)
        if isinstance(exc, OllamaCancelledError):
            return  # cancel_correction() already updated the popup
        if not isinstance(exc, OllamaError):
            log.error("Correction failed", exc_info=exc)
        else:
            log.warning("AI error: %s", type(exc).__name__)  # type only, never text
            if isinstance(exc, OllamaConnectionError):
                self.refresh_ollama(quiet=True)
        self.popup.show_error("AI error")

    # ================================================================== popup actions
    def accept_correction(self) -> None:
        sess = self._session
        if not sess or not sess.result or not sess.target:
            return
        s = self.settings
        corrected = sess.result.corrected
        self.popup.set_busy(f"Replacing text in {sess.target.app_label}...")
        sid = sess.id

        def work() -> ReplaceResult:
            return replace_selection(
                sess.target, sess.original, corrected, verify=s.verify_before_replace,
                restore_clipboard=s.restore_clipboard, restore_delay_ms=s.clipboard_restore_delay_ms,
                copy_timeout_ms=s.copy_timeout_ms, select_all_first=sess.select_all,
            )

        def done(rr: ReplaceResult) -> None:
            if not self._current(sid):
                return
            if rr.outcome is ReplaceOutcome.REPLACED:
                if s.close_popup_after_replace:
                    self.popup.hide()
                    self._session = None
                else:
                    self.popup.end_busy()
                    self.popup.accept_btn.setEnabled(False)
                    self.popup.show_info("✔ " + rr.message, "ok")
            else:
                self.popup.end_busy()
                self.popup.accept_btn.setEnabled(False)
                self.popup.show_info(rr.message, "warn" if rr.outcome is ReplaceOutcome.COPIED else "err")
                if not self.popup.isVisible():
                    self.notify("Copied instead of replaced", rr.message)

        def failed(exc: BaseException) -> None:
            log.error("Replace failed", exc_info=exc)
            if self._current(sid):
                self.popup.end_busy()
                self.popup.show_info("Replacing failed. Use Copy and paste the text yourself.", "err")

        run_background(self.invoker, work, done, failed, name="LocalWriteReplace")

    def copy_correction(self) -> None:
        sess = self._session
        if sess and sess.result:
            if self.copy_text(sess.result.corrected):
                self.popup.show_info("✔ Copied - paste it anywhere with Ctrl+V.", "ok")

    def copy_text(self, text: str) -> bool:
        try:
            clipboard.set_text(text)
            return True
        except clipboard.ClipboardError as exc:
            self.notify("Copy failed", str(exc), error=True)
            if self.popup.isVisible():
                self.popup.show_info(f"Copy failed: {exc}", "err")
            return False

    def retry_correction(self) -> None:
        sess = self._session
        if sess:
            sess.retries += 1
            self._run_correction(sess, temperature_boost=min(0.6, 0.25 * sess.retries))

    def change_mode(self, key: str) -> None:
        sess = self._session
        if not sess or key not in MODES:
            return
        if key == "custom":
            got = self._ask_custom_instruction()
            if got is None:
                self.popup.set_context(sess.mode_key, self.settings.model, sess.target is not None)
                return
            sess.custom_instruction = got
        sess.mode_key = key
        sess.retries = 0
        self.popup.set_context(key, self.settings.model, can_replace=sess.target is not None,
                               source_note={"clipboard": "from clipboard", "realtime": "real-time"}.get(
                                   sess.source, sess.target.app_label if sess.target else ""))
        self._run_correction(sess)

    def cancel_correction(self) -> None:
        sess = self._session
        if sess and sess.cancel and sess.result is None:
            sess.cancel.cancel("user")
            self._set_busy(False)
            self.popup.show_error("Correction cancelled", "", "Press Retry to run it again or choose another mode.")

    def close_popup(self) -> None:
        if self._session and self._session.cancel and self._session.result is None:
            self._session.cancel.cancel("user")
        self._session = None
        self._set_busy(False)
        self.popup.hide()

    # ================================================================== other entry points
    def correct_clipboard(self) -> None:
        try:
            text = clipboard.get_text()
        except clipboard.ClipboardError as exc:
            self.notify("Clipboard busy", str(exc), error=True)
            return
        if not text or not text.strip():
            self.notify("Clipboard is empty", "Copy some text first, then choose 'Correct clipboard text'.")
            return
        self.start_session(text[:20_000], self.settings.default_mode, None, "clipboard", anchor=QCursor.pos())

    def open_realtime_suggestion(self, fld: TextField, original: str, corrected: str) -> None:
        target = dataclasses.replace(fld.target, focus_hwnd=fld.hwnd)
        result = CorrectionResult(original, corrected, "quick", self.settings.model, 0.0)
        anchor = physical_to_logical(fld.rect[0], fld.rect[3]) or QCursor.pos()
        self.start_session(original, "quick", target, "realtime", select_all=True, result=result, anchor=anchor)

    def playground_correct(self, text: str, mode: str, on_progress, on_done,
                           custom_instruction: str = "") -> CancelToken | None:
        """Correct text typed in the Writing Assistant. Returns a token to cancel the request."""
        engine = self.make_engine()
        if not engine.model:
            on_done(None, OllamaError("No AI model selected",
                                      hint="Choose a model on the Home page or in Settings."))
            return None
        token = CancelToken()
        self._set_busy(True)
        instruction = custom_instruction or self.settings.custom_instruction

        def progress(partial: str) -> None:
            if not token.cancelled:
                self.invoker.call(on_progress, partial)

        def ok(res) -> None:
            self._set_busy(False)
            if not token.cancelled:
                on_done(res, None)

        def bad(exc) -> None:
            self._set_busy(False)
            if not token.cancelled:
                on_done(None, exc)

        run_background(self.invoker, lambda: engine.correct(text, mode, instruction, on_progress=progress,
                                                            cancel=token), ok, bad)
        return token

    def test_model(self, model: str, done, url: str | None = None) -> None:
        if not model:
            done(False, "Choose a model first.")
            return
        engine = self.make_engine(model=model, url=url)
        engine.timeout = max(120, engine.timeout)

        def ok(res: CorrectionResult) -> None:
            done(True, f"{model} works ({res.elapsed:.1f}s): “{res.corrected.strip()}”")
            self.refresh_ollama(quiet=True)

        def bad(exc) -> None:
            if isinstance(exc, OllamaError):
                done(False, f"{exc.title}. {exc.hint.splitlines()[0] if exc.hint else ''}")
            else:
                done(False, str(exc))

        run_background(self.invoker, lambda: engine.correct(TEST_SENTENCE, "grammar"), ok, bad)

    def test_connection(self, url: str, done) -> None:
        def work():
            client = OllamaClient(url)
            return client.version(), client.list_models()

        def ok(res) -> None:
            version, models = res
            done(True, f"Connected to Ollama {version} · {len(models)} model(s) installed")

        def bad(exc) -> None:
            done(False, getattr(exc, "title", str(exc)))

        run_background(self.invoker, work, ok, bad)

    def check_ollama_from_tray(self) -> None:
        def report() -> None:
            st = self.ollama_status
            if st.state == "ok":
                model = self.settings.model or "no model selected"
                self.notify("Ollama is running",
                            f"Version {st.version} \u00b7 {len(st.models)} model(s) \u00b7 using {model}", force=True)
            else:
                self.notify("Ollama is not reachable", "Start Ollama from the Start menu, then try again.",
                            error=True)

        self.refresh_ollama(then=report)

    def refresh_ollama(self, url: str | None = None, quiet: bool = False, then=None) -> None:
        target_url = url or self.settings.ollama_url
        if not quiet:
            self.ollama_status = dataclasses.replace(self.ollama_status, state="checking")
            self.status_changed.emit()

        def work():
            client = OllamaClient(target_url)
            return client.version(), client.list_models()

        def ok(res) -> None:
            version, models = res
            self.ollama_status = OllamaStatus("ok", version, models)
            self.status_changed.emit()
            if then:
                then()

        def bad(exc) -> None:
            title = getattr(exc, "title", "Ollama is not available")
            hint = getattr(exc, "hint", "") or TROUBLESHOOTING
            self.ollama_status = OllamaStatus("error", "", [], title, hint)
            self.status_changed.emit()
            if then:
                then()

        run_background(self.invoker, work, ok, bad, name="LocalWriteStatus")

    # ================================================================== windows
    def show_main_window(self, page: str | None = None, entry_id: int | None = None) -> None:
        if page:
            self.main_window.show_page(page, entry_id)
        self.main_window.bring_to_front()

    def run_setup_wizard(self) -> None:
        if self._wizard is None or not self._wizard.isVisible():
            self._wizard = SetupWizard(self)
        self._wizard.show()
        self._wizard.raise_()
        self._wizard.activateWindow()
