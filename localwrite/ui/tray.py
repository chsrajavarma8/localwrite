"""System tray icon and menu."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from localwrite.core.modes import MODE_ORDER, MODES
from localwrite.ui.icons import app_icon

if TYPE_CHECKING:
    from localwrite.app_controller import AppController


class TrayIcon:
    def __init__(self, controller: "AppController") -> None:
        self.c = controller
        self.icon = QSystemTrayIcon(app_icon())
        self.icon.setToolTip("LocalWrite")
        menu = QMenu()
        self.menu = menu
        self.status_action = QAction("Starting...", menu)
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)
        menu.addSeparator()

        open_action = QAction("Open LocalWrite", menu)
        open_action.triggered.connect(lambda: self.c.show_main_window("home"))
        menu.addAction(open_action)

        check = QAction("Check Ollama status", menu)
        check.triggered.connect(self.c.check_ollama_from_tray)
        menu.addAction(check)
        menu.addSeparator()

        self.enabled_action = QAction("Global shortcuts enabled", menu)
        self.enabled_action.setCheckable(True)
        self.enabled_action.toggled.connect(self.c.set_enabled)
        menu.addAction(self.enabled_action)

        mode_menu = menu.addMenu("Correction mode")
        group = QActionGroup(mode_menu)
        self.mode_actions: dict[str, QAction] = {}
        for key in MODE_ORDER:
            act = QAction(MODES[key].label, mode_menu)
            act.setCheckable(True)
            act.triggered.connect(lambda _=False, k=key: self.c.set_default_mode(k))
            group.addAction(act)
            mode_menu.addAction(act)
            self.mode_actions[key] = act

        clip = QAction("Correct clipboard text", menu)
        clip.triggered.connect(self.c.correct_clipboard)
        menu.addAction(clip)

        self.realtime_action = QAction("Real-time spelling assistance", menu)
        self.realtime_action.setCheckable(True)
        self.realtime_action.toggled.connect(self.c.set_realtime_enabled)
        menu.addAction(self.realtime_action)
        menu.addSeparator()

        assistant = QAction("Writing Assistant", menu)
        assistant.triggered.connect(lambda: self.c.show_main_window("assistant"))
        settings = QAction("Settings...", menu)
        settings.triggered.connect(lambda: self.c.show_main_window("settings"))
        menu.addAction(assistant)
        menu.addAction(settings)
        menu.addSeparator()
        quit_action = QAction("Exit LocalWrite", menu)
        quit_action.triggered.connect(self.c.quit)
        menu.addAction(quit_action)

        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._activated)
        self.c.status_changed.connect(self.refresh)
        self.c.settings_changed.connect(self.refresh)

    def show(self) -> None:
        self.icon.show()
        self.refresh()

    def hide(self) -> None:
        self.icon.hide()

    def _activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.c.show_main_window()

    def refresh(self) -> None:
        s = self.c.settings
        st = self.c.ollama_status
        if not s.assistant_enabled:
            state, status = "disabled", "Shortcuts paused"
        elif st.state == "error":
            state, status = "error", "Ollama not connected"
        elif self.c.busy:
            state, status = "busy", "Working..."
        else:
            state, status = "normal", "Ready"
        self.icon.setIcon(app_icon(state, live_dot=s.realtime_enabled and s.assistant_enabled))
        mode = MODES[s.default_mode].label
        model = s.model or "no model"
        live = " · real-time ON" if s.realtime_enabled else ""
        self.icon.setToolTip(f"LocalWrite - {status}\n{model} · {mode}{live}\n{s.hotkeys.get('general', '')} to correct")
        self.status_action.setText(f"{status} · {model}")
        for w, val in ((self.enabled_action, s.assistant_enabled), (self.realtime_action, s.realtime_enabled)):
            w.blockSignals(True)
            w.setChecked(val)
            w.blockSignals(False)
        if s.default_mode in self.mode_actions:
            self.mode_actions[s.default_mode].setChecked(True)

    def notify(self, title: str, message: str, error: bool = False) -> None:
        icon = QSystemTrayIcon.MessageIcon.Warning if error else QSystemTrayIcon.MessageIcon.Information
        self.icon.showMessage(title, message, icon, 6000)
