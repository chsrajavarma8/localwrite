"""Settings: grouped cards of setting rows, saved explicitly with a bottom save bar."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QKeySequenceEdit, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from localwrite import __version__, paths
from localwrite.config.settings import (
    DEFAULT_EXCLUDED_APPS, DEFAULT_HOTKEYS, HOTKEY_LABELS, POPUP_POSITION_LABELS, POPUP_POSITIONS,
    RECOMMENDED_MODEL, Settings,
)
from localwrite.core.modes import MODE_ORDER, MODES
from localwrite.ui import theme
from localwrite.ui.icons import line_icon
from localwrite.ui.widgets import (
    Card, SettingRow, Spinner, ToggleSwitch, divider, icon_label, muted_label, set_variant, soft_shadow,
)
from localwrite.win.hotkeys import HotkeyParseError, normalize_hotkey, validate_global_hotkey

if TYPE_CHECKING:
    from localwrite.app_controller import AppController

CONTROL_W = 300


def _to_qt(combo: str) -> QKeySequence:
    return QKeySequence.fromString(combo.replace("Win+", "Meta+"), QKeySequence.SequenceFormat.PortableText)


def _from_qt(seq: QKeySequence) -> str:
    return seq.toString(QKeySequence.SequenceFormat.PortableText).replace("Meta+", "Win+")


class _HotkeyFocusFilter(QObject):
    """Pause global hotkeys while a shortcut field is focused so the combination can be recorded."""

    def __init__(self, controller: "AppController") -> None:
        super().__init__()
        self.c = controller

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.FocusIn:
            self.c.suspend_hotkeys()
        elif event.type() == QEvent.Type.FocusOut:
            self.c.resume_hotkeys()
        return False


class HotkeyField(QWidget):
    def __init__(self, action: str, focus_filter: QObject) -> None:
        super().__init__()
        self.action = action
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.edit = QKeySequenceEdit()
        self.edit.setMaximumSequenceLength(1)
        self.edit.installEventFilter(focus_filter)
        self.edit.setToolTip("Click, then press the new key combination")
        clear = set_variant(QPushButton("Clear"), "ghost")
        clear.clicked.connect(self.edit.clear)
        reset = set_variant(QPushButton("Reset"), "ghost")
        reset.setToolTip(f"Default: {DEFAULT_HOTKEYS[action]}")
        reset.clicked.connect(lambda: self.set_value(DEFAULT_HOTKEYS[action]))
        row.addWidget(self.edit, 1)
        row.addWidget(clear)
        row.addWidget(reset)
        lay.addLayout(row)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.hide()
        lay.addWidget(self.error)
        self.edit.keySequenceChanged.connect(lambda _s: self.validate())

    def set_value(self, combo: str) -> None:
        self.edit.setKeySequence(_to_qt(combo) if combo else QKeySequence())
        self.validate()

    def value(self) -> str:
        return _from_qt(self.edit.keySequence())

    def validate(self, runtime_error: str | None = None) -> bool:
        combo = self.value()
        msg = None
        if combo:
            try:
                normalize_hotkey(combo)
                msg = validate_global_hotkey(combo, allow_bare=self.action == "close_popup")
            except HotkeyParseError as exc:
                msg = str(exc)
        shown = msg or runtime_error
        self.error.setText(shown or "")
        self.error.setStyleSheet(f"color: {theme.current().danger}; font-size: 9pt;")
        self.error.setVisible(bool(shown))
        return msg is None


class Section(Card):
    """A settings card whose rows are separated by hairline dividers."""

    def __init__(self, title: str, icon: str, subtitle: str = "") -> None:
        super().__init__(title, icon, subtitle, shadow=False)
        self.body.setSpacing(0)
        if self.header is not None:
            self.body.setStretch(0, 0)
        self._rows = 0

    def add(self, row: QWidget) -> QWidget:
        if self._rows:
            self.body.addWidget(divider())
        elif self.header is not None:
            self.body.addSpacing(6)
        self.body.addWidget(row)
        self._rows += 1
        return row


def _toggle() -> ToggleSwitch:
    return ToggleSwitch()


class SettingsPage(QWidget):
    def __init__(self, controller: "AppController") -> None:
        super().__init__()
        self.c = controller
        self.setObjectName("Page")
        p = theme.current()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll, 1)
        body = QWidget()
        body.setObjectName("PageBody")
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(36, 30, 36, 30)
        lay.setSpacing(18)
        title = QLabel("Settings")
        title.setObjectName("PageTitle")
        sub = QLabel("Changes take effect when you press Save.")
        sub.setObjectName("PageSubtitle")
        lay.addWidget(title)
        lay.addWidget(sub)

        # ---------------- AI engine
        s = Section("Local AI engine", "server", "LocalWrite uses Ollama on this computer. Nothing is sent online.")
        url_box = QWidget()
        ub = QHBoxLayout(url_box)
        ub.setContentsMargins(0, 0, 0, 0)
        ub.setSpacing(6)
        self.url = QLineEdit()
        self.url.setPlaceholderText("http://localhost:11434")
        self.test_conn_btn = QPushButton("Test connection")
        self.test_conn_btn.clicked.connect(self._test_connection)
        ub.addWidget(self.url, 1)
        ub.addWidget(self.test_conn_btn)
        s.add(SettingRow("Ollama server address", "Default: http://localhost:11434", url_box, control_width=CONTROL_W + 120))
        self.url_status = QLabel()
        self.url_status.setWordWrap(True)
        self.url_status.hide()
        s.body.addWidget(self.url_status)

        model_box = QWidget()
        mb = QHBoxLayout(model_box)
        mb.setContentsMargins(0, 0, 0, 0)
        mb.setSpacing(6)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        refresh = QPushButton()
        refresh.setIcon(line_icon("refresh", p.text_soft, 16))
        refresh.setToolTip("Refresh installed models")
        refresh.setFixedWidth(38)
        refresh.clicked.connect(lambda: self.c.refresh_ollama(url=self.url.text()))
        self.test_model_btn = QPushButton("Test")
        self.test_model_btn.setToolTip("Run a sample correction with this model")
        self.test_model_btn.clicked.connect(self._test_model)
        self.model_spinner = Spinner(16)
        mb.addWidget(self.model, 1)
        mb.addWidget(refresh)
        mb.addWidget(self.test_model_btn)
        mb.addWidget(self.model_spinner)
        s.add(SettingRow("AI model", f"Any installed Ollama model. Lightweight and recommended: {RECOMMENDED_MODEL}. "
                                     "Models are never downloaded without your permission.",
                         model_box, control_width=CONTROL_W + 120))
        self.model_status = QLabel()
        self.model_status.setWordWrap(True)
        self.model_status.hide()
        s.body.addWidget(self.model_status)

        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 1.5)
        self.temperature.setSingleStep(0.05)
        self.temperature.setDecimals(2)
        s.add(SettingRow("AI temperature", "Lower is more precise and predictable. Correction modes always stay "
                                           "at 0.15 or below.", self.temperature, control_width=CONTROL_W))
        self.timeout = QSpinBox()
        self.timeout.setRange(10, 600)
        self.timeout.setSuffix(" seconds")
        s.add(SettingRow("Response timeout", "Give up if the model takes longer than this.", self.timeout,
                         control_width=CONTROL_W))
        self.keep_alive = QLineEdit()
        s.add(SettingRow("Keep model loaded", "How long Ollama keeps the model in memory after use, e.g. 15m, 1h, 0.",
                         self.keep_alive, control_width=CONTROL_W))
        self.context = QComboBox()
        for n in (2048, 4096, 8192, 16384, 32768):
            self.context.addItem(f"{n:,} tokens", n)
        s.add(SettingRow("Context window", "Larger handles longer text in one pass but uses more memory.",
                         self.context, control_width=CONTROL_W))
        self.update_status = muted_label(small=True)
        s.add(SettingRow("Ollama updates", "LocalWrite never updates Ollama itself. Update it from the Ollama icon "
                                           "in the system tray or with the official installer.", self.update_status,
                         control_width=CONTROL_W))
        self.check_online = _toggle()
        s.add(SettingRow("Check online for Ollama updates (optional)",
                         "Off by default. Asks GitHub for the latest Ollama version number. Nothing about you or "
                         "your writing is sent. Without it, LocalWrite still notices updates Ollama has announced "
                         "on this PC.", self.check_online))
        lay.addWidget(s)

        # ---------------- Writing
        s = Section("Writing", "pen")
        self.default_mode = QComboBox()
        for key in MODE_ORDER:
            self.default_mode.addItem(MODES[key].label, key)
        s.add(SettingRow("Default correction mode", "Used by the general shortcut.", self.default_mode,
                         control_width=CONTROL_W))
        self.custom_instruction = QPlainTextEdit()
        self.custom_instruction.setPlaceholderText("e.g. Rewrite as a friendly reply to a customer")
        self.custom_instruction.setFixedHeight(72)
        s.add(SettingRow("Custom instructions", "Used by the Custom Instructions mode.", self.custom_instruction,
                         stacked=True))
        lay.addWidget(s)

        # ---------------- Shortcuts
        s = Section("Keyboard shortcuts", "keyboard",
                    "Click a field and press a new combination. Shortcuts pause while you edit them.")
        self.enabled = _toggle()
        s.add(SettingRow("Enable global shortcuts", "Turn off to pause LocalWrite in every app.", self.enabled))
        self._focus_filter = _HotkeyFocusFilter(self.c)
        self.hotkey_fields: dict[str, HotkeyField] = {}
        for action, label in HOTKEY_LABELS.items():
            f = HotkeyField(action, self._focus_filter)
            self.hotkey_fields[action] = f
            desc = "Only active while the popup is open" if action == "close_popup" else ""
            s.add(SettingRow(label, desc, f, control_width=CONTROL_W + 60))
        lay.addWidget(s)

        # ---------------- Popup
        s = Section("Correction popup", "window")
        self.popup_position = QComboBox()
        for key in POPUP_POSITIONS:
            self.popup_position.addItem(POPUP_POSITION_LABELS[key], key)
        s.add(SettingRow("Popup position", "Where the popup appears after you press a shortcut.",
                         self.popup_position, control_width=CONTROL_W))
        self.close_after_replace = _toggle()
        s.add(SettingRow("Close after replacing", "Hide the popup once the text has been replaced.",
                         self.close_after_replace))
        lay.addWidget(s)

        # ---------------- Clipboard
        s = Section("Clipboard & replacement", "clipboard")
        self.restore_clipboard = _toggle()
        s.add(SettingRow("Restore my clipboard", "Put back whatever you had copied after LocalWrite borrows the "
                                                 "clipboard to read or paste text.", self.restore_clipboard))
        self.verify = _toggle()
        s.add(SettingRow("Verify selection before replacing", "Only replace if the same text is still selected in "
                                                              "the same window. Strongly recommended.", self.verify))
        self.restore_delay = QSpinBox()
        self.restore_delay.setRange(100, 5000)
        self.restore_delay.setSingleStep(100)
        self.restore_delay.setSuffix(" ms")
        s.add(SettingRow("Wait before restoring", "Increase if a slow app pastes your old clipboard content.",
                         self.restore_delay, control_width=CONTROL_W))
        self.copy_timeout = QSpinBox()
        self.copy_timeout.setRange(200, 5000)
        self.copy_timeout.setSingleStep(100)
        self.copy_timeout.setSuffix(" ms")
        s.add(SettingRow("Wait for selected text", "Increase if an app is slow to copy the selection.",
                         self.copy_timeout, control_width=CONTROL_W))
        lay.addWidget(s)

        # ---------------- System
        s = Section("Windows integration", "window")
        self.start_with_windows = _toggle()
        s.add(SettingRow("Start with Windows", "Off by default. When on, LocalWrite starts quietly in the system "
                                               "tray when you sign in to Windows.", self.start_with_windows))
        self.start_minimized = _toggle()
        s.add(SettingRow("Start in the system tray", "Don't open the main window at startup.", self.start_minimized))
        self.minimize_to_tray = _toggle()
        s.add(SettingRow("Minimize to system tray", "Minimizing hides the window to the tray.", self.minimize_to_tray))
        self.close_to_tray = _toggle()
        s.add(SettingRow("Keep running when closed", "Closing the window keeps shortcuts working from the tray.",
                         self.close_to_tray))
        self.notifications = _toggle()
        s.add(SettingRow("Notifications", "Show tray notifications for important events.", self.notifications))
        lay.addWidget(s)

        # ---------------- Privacy
        s = Section("Privacy", "shield")
        for title_, desc in (
            ("No correction history", "Text is processed in memory and discarded after each correction. "
                                      "Nothing you write is ever saved to disk."),
            ("100% local processing", "Text goes only to your Ollama server. LocalWrite ignores system proxies."),
            ("No background monitoring", "Text is read only when you press a shortcut. Logs never contain your text."),
        ):
            s.add(SettingRow(title_, desc, icon_label("check", p.success, 18)))
        self.realtime = _toggle()
        s.add(SettingRow("Real-time spelling assistance (optional)",
                         "Off by default. Checks classic Windows text fields (like Notepad) when you pause typing and "
                         "shows a small badge. Never reads password fields, sign-in windows or the apps below. "
                         "An orange dot on the tray icon shows when it's on.", self.realtime))
        self.excluded = QLineEdit()
        self.excluded.setPlaceholderText(", ".join(DEFAULT_EXCLUDED_APPS[:3]) + ", ...")
        s.add(SettingRow("Never read these apps", "Comma-separated program names for real-time assistance.",
                         self.excluded, control_width=CONTROL_W + 60))
        folder = QPushButton("Open settings folder")
        folder.clicked.connect(lambda: os.startfile(str(paths.data_dir())))  # noqa: S606
        s.add(SettingRow("Local files", "Only your settings and technical logs (without any text) are stored here.",
                         folder))
        lay.addWidget(s)

        # ---------------- Setup
        s = Section("Setup", "sparkle")
        wiz = QPushButton("Run setup guide")
        wiz.clicked.connect(self.c.run_setup_wizard)
        s.add(SettingRow("Setup guide", "Re-check Ollama, choose a model and run a test correction.", wiz))
        s.add(SettingRow("Version", f"LocalWrite {__version__}", None))
        lay.addWidget(s)
        lay.addStretch(1)

        # ---------------- save bar
        bar = QFrame()
        bar.setObjectName("Card")
        bar.setStyleSheet("#Card { border-radius: 0; border-left: none; border-right: none; border-bottom: none; }")
        soft_shadow(bar, blur=20, dy=-2, alpha=14)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(36, 12, 36, 12)
        self.save_status = muted_label(wrap=False)
        defaults = set_variant(QPushButton("Restore defaults"), "ghost")
        defaults.clicked.connect(self._defaults)
        revert = QPushButton("Revert")
        revert.clicked.connect(lambda: self.load())
        self.save_btn = set_variant(QPushButton("Save changes"), "primary")
        self.save_btn.clicked.connect(self.save)
        bl.addWidget(self.save_status, 1)
        bl.addWidget(defaults)
        bl.addWidget(revert)
        bl.addWidget(self.save_btn)
        outer.addWidget(bar)

        self.c.status_changed.connect(self._fill_models)
        self.c.status_changed.connect(self._update_update_status)
        self.load()

    # ------------------------------------------------------------------ load / save
    def load(self, settings: Settings | None = None) -> None:
        s = settings or self.c.settings
        self.url.setText(s.ollama_url)
        self._fill_models(selected=s.model)
        self.temperature.setValue(s.temperature)
        self.timeout.setValue(s.timeout_seconds)
        self.keep_alive.setText(s.keep_alive)
        idx = self.context.findData(s.context_length)
        if idx < 0:
            self.context.addItem(f"{s.context_length:,} tokens", s.context_length)
            idx = self.context.count() - 1
        self.context.setCurrentIndex(idx)
        self.default_mode.setCurrentIndex(max(0, self.default_mode.findData(s.default_mode)))
        self.custom_instruction.setPlainText(s.custom_instruction)
        self.enabled.setChecked(s.assistant_enabled)
        for action, f in self.hotkey_fields.items():
            f.set_value(s.hotkeys.get(action, ""))
            f.validate(self.c.hotkey_errors.get(action))
        self.popup_position.setCurrentIndex(max(0, self.popup_position.findData(s.popup_position)))
        self.close_after_replace.setChecked(s.close_popup_after_replace)
        self.restore_clipboard.setChecked(s.restore_clipboard)
        self.verify.setChecked(s.verify_before_replace)
        self.restore_delay.setValue(s.clipboard_restore_delay_ms)
        self.copy_timeout.setValue(s.copy_timeout_ms)
        self.start_with_windows.setChecked(s.start_with_windows)
        self.start_minimized.setChecked(s.start_minimized)
        self.minimize_to_tray.setChecked(s.minimize_to_tray)
        self.close_to_tray.setChecked(s.close_to_tray)
        self.notifications.setChecked(s.show_notifications)
        self.realtime.setChecked(s.realtime_enabled)
        self.excluded.setText(", ".join(s.realtime_excluded_apps))
        self.check_online.setChecked(s.check_ollama_updates_online)
        self._update_update_status()
        self.save_status.setText("")
        self.save_status.setStyleSheet("")
        self._update_url_warning()

    def collect(self) -> Settings:
        return self.c.settings.copy(
            ollama_url=self.url.text(),
            model=self.model.currentText().strip(),
            temperature=self.temperature.value(),
            timeout_seconds=self.timeout.value(),
            keep_alive=self.keep_alive.text(),
            context_length=self.context.currentData(),
            default_mode=self.default_mode.currentData(),
            custom_instruction=self.custom_instruction.toPlainText(),
            assistant_enabled=self.enabled.isChecked(),
            hotkeys={a: f.value() for a, f in self.hotkey_fields.items()},
            popup_position=self.popup_position.currentData(),
            close_popup_after_replace=self.close_after_replace.isChecked(),
            restore_clipboard=self.restore_clipboard.isChecked(),
            verify_before_replace=self.verify.isChecked(),
            clipboard_restore_delay_ms=self.restore_delay.value(),
            copy_timeout_ms=self.copy_timeout.value(),
            start_with_windows=self.start_with_windows.isChecked(),
            start_minimized=self.start_minimized.isChecked(),
            minimize_to_tray=self.minimize_to_tray.isChecked(),
            close_to_tray=self.close_to_tray.isChecked(),
            show_notifications=self.notifications.isChecked(),
            realtime_enabled=self.realtime.isChecked(),
            check_ollama_updates_online=self.check_online.isChecked(),
            realtime_excluded_apps=[a.strip() for a in self.excluded.text().split(",") if a.strip()],
        )

    def save(self) -> None:
        p = theme.current()
        bad = [f for f in self.hotkey_fields.values() if f.value() and not f.validate()]
        if bad:
            self._status("Please fix the highlighted shortcuts first.", p.danger)
            return
        values = [f.value() for f in self.hotkey_fields.values() if f.value()]
        if len({normalize_hotkey(v) for v in values}) != len(values):
            self._status("Two actions use the same shortcut.", p.danger)
            return
        errors = self.c.apply_settings(self.collect())
        for action, f in self.hotkey_fields.items():
            f.validate(errors.get(action))
        if any(errors.values()):
            self._status("Saved. Some shortcuts are used by another app - choose different ones.", p.warning)
        else:
            self._status("✔ Settings saved", p.success)
        self._update_url_warning()

    def _status(self, text: str, color: str) -> None:
        self.save_status.setText(text)
        self.save_status.setStyleSheet(f"color: {color}; font-weight: 600;")

    def _defaults(self) -> None:
        self.load(Settings(model=self.c.settings.model, first_run_complete=True).validated())
        self._status("Defaults loaded - press Save to apply.", theme.current().muted)

    # ------------------------------------------------------------------ helpers
    def _fill_models(self, selected: str | None = None) -> None:
        current = selected if isinstance(selected, str) else self.model.currentText()
        names = [m.name for m in self.c.ollama_status.models if not m.is_embedding_model]
        self.model.blockSignals(True)
        self.model.clear()
        for n in names:
            self.model.addItem(n)
        if current and current not in names:
            self.model.addItem(current)
        self.model.setCurrentText(current or "")
        self.model.blockSignals(False)

    def _update_update_status(self) -> None:
        st = self.c.ollama_status
        upd = self.c.ollama_update
        if st.state != "ok":
            text = "Unknown until Ollama is connected"
        elif upd:
            text = f"Ollama {upd.latest} is available (you have {upd.installed})"
        else:
            text = f"No update found (you have {st.version})"
        self.update_status.setText(text)

    def _update_url_warning(self) -> None:
        if not self.c.settings.is_local_server():
            self._row_status(self.url_status, "This server is not on this computer - your text would travel over "
                                              "the network.", theme.current().warning)
        else:
            self.url_status.hide()

    @staticmethod
    def _row_status(label: QLabel, text: str, color: str) -> None:
        label.setText(text)
        label.setStyleSheet(f"color: {color}; font-size: 9pt; padding: 0 0 10px 0;")
        label.show()

    def _test_connection(self) -> None:
        self.test_conn_btn.setEnabled(False)
        self._row_status(self.url_status, "Connecting...", theme.current().muted)

        def done(ok: bool, message: str) -> None:
            self.test_conn_btn.setEnabled(True)
            p = theme.current()
            self._row_status(self.url_status, ("✔ " if ok else "") + message, p.success if ok else p.danger)

        self.c.test_connection(self.url.text(), done)

    def _test_model(self) -> None:
        self.test_model_btn.setEnabled(False)
        self.model_spinner.start()
        self._row_status(self.model_status, "Running a sample correction...", theme.current().muted)

        def done(ok: bool, message: str) -> None:
            self.test_model_btn.setEnabled(True)
            self.model_spinner.stop()
            p = theme.current()
            self._row_status(self.model_status, ("✔ " if ok else "") + message, p.success if ok else p.danger)

        self.c.test_model(self.model.currentText().strip(), done, url=self.url.text())
