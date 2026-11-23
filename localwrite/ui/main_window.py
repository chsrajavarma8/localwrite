"""Main window: a minimal sidebar (Home, Writing Assistant, Settings, About) and the pages."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from localwrite import __version__
from localwrite.ui import theme
from localwrite.ui.about_page import AboutPage
from localwrite.ui.assistant_page import AssistantPage
from localwrite.ui.home_page import HomePage
from localwrite.ui.icons import app_icon, line_icon
from localwrite.ui.settings_page import SettingsPage
from localwrite.ui.widgets import StatusPill, muted_label

if TYPE_CHECKING:
    from localwrite.app_controller import AppController

NAV = (
    ("home", "Home", "home"),
    ("assistant", "Writing Assistant", "pen"),
    ("settings", "Settings", "settings"),
    ("about", "About", "info"),
)
# Old page names still accepted by show_page().
_ALIASES = {"dashboard": "home", "help": "about"}


class MainWindow(QMainWindow):
    PAGES = tuple(key for key, _l, _i in NAV)

    def __init__(self, controller: "AppController") -> None:
        super().__init__()
        self.c = controller
        self.setWindowTitle("LocalWrite")
        self.setWindowIcon(app_icon())
        self.resize(1120, 780)
        self.setMinimumSize(820, 580)
        self._tray_hint_shown = False
        p = theme.current()

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(232)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(16, 22, 16, 18)
        sl.setSpacing(4)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(34, 34))
        names = QVBoxLayout()
        names.setSpacing(0)
        t = QLabel("LocalWrite")
        t.setObjectName("AppTitle")
        names.addWidget(t)
        names.addWidget(muted_label("Private AI writing", wrap=False, small=True))
        brand.addWidget(logo)
        brand.addLayout(names, 1)
        sl.addLayout(brand)
        sl.addSpacing(26)

        self.stack = QStackedWidget()
        self.pages = {
            "home": HomePage(controller, lambda: self.show_page("assistant")),
            "assistant": AssistantPage(controller),
            "settings": SettingsPage(controller),
            "about": AboutPage(controller),
        }
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        self._nav_icons = {key: icon for key, _l, icon in NAV}
        for key, label, _icon in NAV:
            btn = QPushButton("  " + label)
            btn.setProperty("nav", True)
            btn.setCheckable(True)
            btn.setIconSize(QSize(18, 18))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self.show_page(k))
            self.nav.addButton(btn)
            self.nav_buttons[key] = btn
            sl.addWidget(btn)
            self.stack.addWidget(self.pages[key])
        sl.addStretch(1)

        status_box = QFrame()
        status_box.setObjectName("Card")
        sb = QVBoxLayout(status_box)
        sb.setContentsMargins(12, 10, 12, 10)
        sb.setSpacing(3)
        self.side_status = StatusPill("")
        self.side_model = muted_label(wrap=False, small=True)
        sb.addWidget(self.side_status)
        sb.addWidget(self.side_model)
        sl.addWidget(status_box)
        sl.addSpacing(6)
        sl.addWidget(muted_label(f"v{__version__} · 100% local", wrap=False, small=True))

        root.addWidget(side)
        root.addWidget(self.stack, 1)
        controller.status_changed.connect(self._refresh_side)
        controller.settings_changed.connect(self._refresh_side)
        self._refresh_side()
        self.show_page("home")

    def show_page(self, key: str, *_args) -> None:
        key = _ALIASES.get(key, key)
        if key not in self.pages:
            key = "home"
        self.stack.setCurrentWidget(self.pages[key])
        p = theme.current()
        for k, btn in self.nav_buttons.items():
            btn.setChecked(k == key)
            btn.setIcon(line_icon(self._nav_icons[k], p.accent if k == key else p.muted, 18))
        if key == "settings":
            self.c.refresh_startup_state()  # show the real Windows startup state
            self.pages["settings"].load()
        if key == "assistant":
            QTimer.singleShot(0, self.pages["assistant"].focus_editor)

    def _refresh_side(self) -> None:
        s = self.c.settings
        st = self.c.ollama_status
        if not s.assistant_enabled:
            self.side_status.set_state("warn", "Shortcuts paused")
        elif st.state == "ok":
            self.side_status.set_state("ok", "Ready")
        elif st.state == "checking":
            self.side_status.set_state("busy", "Connecting...")
        else:
            self.side_status.set_state("error", "Ollama offline")
        self.side_model.setText(s.model or "No model selected")

    # ------------------------------------------------------------------ tray behaviour
    def closeEvent(self, event) -> None:  # noqa: N802
        if self.c.settings.close_to_tray and not self.c.quitting and self.c.tray_available():
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.c.notify("LocalWrite is still running",
                              f"Press {self.c.settings.hotkeys.get('general')} in any app. "
                              "Right-click the tray icon to exit.")
            return
        super().closeEvent(event)
        if not self.c.quitting:
            self.c.quit()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if (event.type() == QEvent.Type.WindowStateChange and self.isMinimized()
                and self.c.settings.minimize_to_tray and self.c.tray_available()):
            QTimer.singleShot(0, self.hide)

    def bring_to_front(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
