"""Home: welcome, engine/model status, quick start, writing modes and shortcuts."""
from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from localwrite.config.settings import HOTKEY_LABELS, RECOMMENDED_MODEL
from localwrite.core.modes import MODE_ORDER, MODES
from localwrite.ui import theme
from localwrite.ui.icons import line_icon
from localwrite.ui.widgets import (
    Card, ModeTile, Spinner, StatusPill, ToggleSwitch, icon_label, keycaps_row, muted_label, set_variant,
)

if TYPE_CHECKING:
    from localwrite.app_controller import AppController


class ResponsiveGrid(QWidget):
    """Lays out widgets in as many equal columns as fit."""

    def __init__(self, min_col: int = 240, max_cols: int = 4, spacing: int = 16) -> None:
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(spacing)
        self.min_col = min_col
        self.max_cols = max_cols
        self.items: list[QWidget] = []
        self._cols = 0

    def add(self, w: QWidget) -> None:
        self.items.append(w)
        self._reflow(force=True)

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._reflow()

    def _reflow(self, force: bool = False) -> None:
        cols = max(1, min(self.max_cols, len(self.items) or 1, self.width() // self.min_col))
        if cols == self._cols and not force:
            return
        self._cols = cols
        for w in self.items:
            self.grid.removeWidget(w)
        for i, w in enumerate(self.items):
            self.grid.addWidget(w, i // cols, i % cols)
        for c in range(self.max_cols):
            self.grid.setColumnStretch(c, 1 if c < cols else 0)


def _greeting() -> str:
    h = datetime.now().hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 18 else "Good evening"


class HomePage(QWidget):
    def __init__(self, controller: "AppController", open_assistant) -> None:
        super().__init__()
        self.c = controller
        self.setObjectName("Page")
        p = theme.current()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("PageBody")
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(36, 30, 36, 36)
        lay.setSpacing(20)

        # ---------------- header
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        self.greeting = QLabel()
        self.greeting.setObjectName("PageTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("PageSubtitle")
        self.subtitle.setWordWrap(True)
        titles.addWidget(self.greeting)
        titles.addWidget(self.subtitle)
        head.addLayout(titles, 1)
        toggle_box = QHBoxLayout()
        toggle_box.setSpacing(10)
        self.enabled_label = QLabel()
        self.enabled_label.setStyleSheet("font-weight: 600;")
        self.enabled_switch = ToggleSwitch()
        self.enabled_switch.setToolTip("Turn the global keyboard shortcuts on or off")
        self.enabled_switch.toggled.connect(self.c.set_enabled)
        toggle_box.addWidget(self.enabled_label)
        toggle_box.addWidget(self.enabled_switch)
        head.addLayout(toggle_box)
        lay.addLayout(head)

        # ---------------- offline notice
        self.offline = QFrame()
        self.offline.setObjectName("NoticeWarn")
        ol = QHBoxLayout(self.offline)
        ol.setContentsMargins(18, 16, 18, 16)
        ol.setSpacing(14)
        ol.addWidget(icon_label("alert", p.warning, 22), 0, Qt.AlignmentFlag.AlignTop)
        otext = QVBoxLayout()
        otext.setSpacing(6)
        self.offline_title = QLabel()
        self.offline_title.setStyleSheet("font-weight: 700; font-size: 10.5pt; background: transparent;")
        self.offline_hint = QLabel()
        self.offline_hint.setWordWrap(True)
        self.offline_hint.setStyleSheet(f"color: {p.text_soft}; background: transparent;")
        self.offline_hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        obtn = QHBoxLayout()
        retry = set_variant(QPushButton("Retry connection"), "primary")
        retry.clicked.connect(lambda: self.c.refresh_ollama())
        wiz = QPushButton("Open setup guide")
        wiz.clicked.connect(self.c.run_setup_wizard)
        obtn.addWidget(retry)
        obtn.addWidget(wiz)
        obtn.addStretch(1)
        otext.addWidget(self.offline_title)
        otext.addWidget(self.offline_hint)
        otext.addLayout(obtn)
        ol.addLayout(otext, 1)
        lay.addWidget(self.offline)

        # ---------------- status cards
        grid = ResponsiveGrid(min_col=250, max_cols=3)

        eng = Card("Local AI engine", "server")
        self.engine_pill = StatusPill("Checking...")
        self.engine_detail = muted_label(small=True)
        erow = QHBoxLayout()
        self.test_btn = QPushButton("Test connection")
        self.test_btn.clicked.connect(self._test_connection)
        self.test_spinner = Spinner(16)
        erow.addWidget(self.test_btn)
        erow.addWidget(self.test_spinner)
        erow.addStretch(1)
        eng.body.addWidget(self.engine_pill)
        eng.body.addWidget(self.engine_detail)
        eng.body.addStretch(1)
        eng.body.addLayout(erow)
        grid.add(eng)

        mc = Card("AI model", "chip")
        mrow = QHBoxLayout()
        mrow.setSpacing(6)
        self.model_combo = QComboBox()
        self.model_combo.setToolTip("Models installed in Ollama on this computer")
        self.model_combo.activated.connect(self._model_chosen)
        refresh = QPushButton()
        refresh.setIcon(line_icon("refresh", p.text_soft, 16))
        refresh.setToolTip("Refresh the list of installed models")
        refresh.setFixedWidth(38)
        refresh.clicked.connect(lambda: self.c.refresh_ollama())
        mrow.addWidget(self.model_combo, 1)
        mrow.addWidget(refresh)
        self.model_detail = muted_label(small=True)
        mc.body.addLayout(mrow)
        mc.body.addWidget(self.model_detail)
        mc.body.addStretch(1)
        grid.add(mc)

        sc = Card("Start correcting", "sparkle")
        self.start_hint = muted_label("Select text in any app and press")
        self.start_keys = QWidget()
        self.start_keys_lay = QHBoxLayout(self.start_keys)
        self.start_keys_lay.setContentsMargins(0, 0, 0, 0)
        go = set_variant(QPushButton("Open Writing Assistant"), "primary")
        go.setIcon(line_icon("pen", "#ffffff", 16))
        go.clicked.connect(open_assistant)
        sc.body.addWidget(self.start_hint)
        sc.body.addWidget(self.start_keys)
        sc.body.addStretch(1)
        sc.body.addWidget(go, 0, Qt.AlignmentFlag.AlignLeft)
        grid.add(sc)
        lay.addWidget(grid)

        # ---------------- writing modes
        modes = Card("Writing modes", "pen", "Choose the default mode for your general shortcut. "
                                             "You can switch modes anytime from the correction popup.")
        self.mode_grid = ResponsiveGrid(min_col=200, max_cols=4, spacing=10)
        self.tiles: dict[str, ModeTile] = {}
        for key in MODE_ORDER:
            m = MODES[key]
            tile = ModeTile(key, m.label, m.description)
            tile.clicked.connect(self.c.set_default_mode)
            self.tiles[key] = tile
            self.mode_grid.add(tile)
        modes.body.addWidget(self.mode_grid)
        lay.addWidget(modes)

        # ---------------- shortcuts
        sh = Card("Keyboard shortcuts", "keyboard", "Shortcuts only read the text you have selected, when you press "
                                                    "them. LocalWrite never records your typing.")
        self.shortcut_grid = QGridLayout()
        self.shortcut_grid.setHorizontalSpacing(24)
        self.shortcut_grid.setVerticalSpacing(10)
        sh.body.addLayout(self.shortcut_grid)
        lay.addWidget(sh)

        # ---------------- privacy footer
        priv = QFrame()
        priv.setObjectName("NoticeInfo")
        pl = QHBoxLayout(priv)
        pl.setContentsMargins(18, 14, 18, 14)
        pl.setSpacing(12)
        pl.addWidget(icon_label("shield", p.accent, 22))
        ptxt = QLabel("<b>Private by design.</b> Your text is processed by Ollama on this computer, is never "
                      "sent to the internet, and is never saved. Nothing is kept after a correction.")
        ptxt.setWordWrap(True)
        ptxt.setStyleSheet("background: transparent;")
        pl.addWidget(ptxt, 1)
        lay.addWidget(priv)
        lay.addStretch(1)

        self._test_result: tuple[bool, str, float] | None = None
        self.c.status_changed.connect(self.refresh)
        self.c.settings_changed.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------------ refresh
    def refresh(self) -> None:
        s = self.c.settings
        st = self.c.ollama_status
        p = theme.current()
        self.greeting.setText(f"{_greeting()}!")
        general = s.hotkeys.get("general") or "your shortcut"
        self.subtitle.setText(
            f"Welcome to LocalWrite. Select text anywhere and press {general} to polish it, privately."
            if s.assistant_enabled else
            "Welcome to LocalWrite. Global shortcuts are paused - turn them on to correct text in any app."
        )
        self.enabled_switch.blockSignals(True)
        self.enabled_switch.setChecked(s.assistant_enabled)
        self.enabled_switch.blockSignals(False)
        self.enabled_label.setText("Shortcuts on" if s.assistant_enabled else "Shortcuts off")

        local = s.is_local_server()
        if st.state == "ok":
            self.engine_pill.set_state("ok", "Connected")
            self.engine_detail.setText(f"Ollama {st.version} · {s.ollama_url}")
        elif st.state == "checking":
            self.engine_pill.set_state("busy", "Connecting...")
            self.engine_detail.setText(s.ollama_url)
        elif st.state == "error":
            self.engine_pill.set_state("error", "Not connected")
            self.engine_detail.setText(s.ollama_url)
        else:
            self.engine_pill.set_state("unknown", "Unknown")
        if not local:
            self.engine_detail.setText(self.engine_detail.text() + "\nRemote server: text leaves this PC.")
        self.engine_detail.setStyleSheet("")
        if self._test_result and time.monotonic() - self._test_result[2] < 8:
            ok, message, _ = self._test_result
            self.engine_detail.setText(message)
            self.engine_detail.setStyleSheet(f"color: {p.success if ok else p.danger};")

        # Offline / no-model notice
        if st.state == "error":
            self.offline.show()
            self.offline_title.setText("LocalWrite can't reach Ollama")
            self.offline_hint.setText(
                "Ollama runs the AI on your computer. To fix this:\n"
                "1. Start Ollama from the Start menu (a llama icon appears near the clock), or run 'ollama serve'.\n"
                "2. Not installed yet? Download it free from ollama.com/download/windows.\n"
                f"3. Check the server address in Settings (currently {s.ollama_url})."
            )
        elif st.state == "ok" and not [m for m in st.models if not m.is_embedding_model]:
            self.offline.show()
            self.offline_title.setText("No AI model installed yet")
            self.offline_hint.setText(
                f"Install a lightweight model by running:  ollama pull {RECOMMENDED_MODEL}\n"
                "or open the setup guide to download one (it asks for your permission first)."
            )
        else:
            self.offline.hide()

        # Model combo
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        names = [m.name for m in st.models if not m.is_embedding_model]
        if s.model and s.model not in names:
            names.insert(0, s.model)
        for n in names:
            self.model_combo.addItem(n, n)
        if not names:
            self.model_combo.addItem("No models found", "")
        self.model_combo.setCurrentIndex(max(0, self.model_combo.findData(s.model)))
        self.model_combo.blockSignals(False)
        info = next((m for m in st.models if m.name == s.model), None)
        self.model_detail.setStyleSheet("")
        if not s.model:
            self.model_detail.setText(f"Choose a model. Recommended for most PCs: {RECOMMENDED_MODEL}")
        elif info:
            bits = [b for b in (info.parameter_size, info.size_label) if b]
            self.model_detail.setText(" · ".join(bits) + " · runs locally")
        elif st.state == "ok":
            self.model_detail.setText(f"'{s.model}' is not installed. Install it with: ollama pull {s.model}")
            self.model_detail.setStyleSheet(f"color: {p.warning};")
        else:
            self.model_detail.setText("")

        # Quick start keys
        while self.start_keys_lay.count():
            w = self.start_keys_lay.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.start_keys_lay.addWidget(keycaps_row(s.hotkeys.get("general", "")))

        for key, tile in self.tiles.items():
            tile.set_selected(key == s.default_mode)

        # Shortcuts
        while self.shortcut_grid.count():
            item = self.shortcut_grid.takeAt(0)
            w = item.widget()
            if w:
                w.hide()  # deleteLater alone leaves it painted until the event loop runs
                w.setParent(None)
                w.deleteLater()
        for row, (action, label) in enumerate(HOTKEY_LABELS.items()):
            combo = s.hotkeys.get(action, "")
            text = label
            if action == "general":
                text = f"{label} ({MODES[s.default_mode].label})"
            self.shortcut_grid.addWidget(QLabel(text), row, 0)
            self.shortcut_grid.addWidget(keycaps_row(combo), row, 1)
            err = self.c.hotkey_errors.get(action)
            note = QLabel(err or ("while the popup is open" if action == "close_popup" else ""))
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {p.danger if err else p.muted};")
            self.shortcut_grid.addWidget(note, row, 2)
        self.shortcut_grid.setColumnStretch(2, 1)

    # ------------------------------------------------------------------ actions
    def _model_chosen(self, _index: int) -> None:
        name = self.model_combo.currentData()
        if name:
            self.c.set_model(name)

    def _test_connection(self) -> None:
        self.test_btn.setEnabled(False)
        self.test_spinner.start()
        p = theme.current()

        def done(ok: bool, message: str) -> None:
            self.test_btn.setEnabled(True)
            self.test_spinner.stop()
            self._test_result = (ok, message, time.monotonic())
            self.engine_detail.setText(message)
            self.engine_detail.setStyleSheet(f"color: {p.success if ok else p.danger};")
            self.c.refresh_ollama(quiet=True)

        self.c.test_connection(self.c.settings.ollama_url, done)
