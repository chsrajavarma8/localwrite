"""Writing Assistant: correct text inside LocalWrite itself.

Text typed here lives only in memory; it is never written to disk and is
discarded when cleared or when the app closes.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QTextBrowser,
    QVBoxLayout, QWidget,
)

from localwrite.core.diff import change_count, compute_diff, plain_html, render_inline
from localwrite.core.modes import MODE_ORDER, MODES
from localwrite.ui import theme
from localwrite.ui.icons import line_icon
from localwrite.core.ollama_client import OllamaCancelledError
from localwrite.ui.widgets import Card, ErrorBanner, FlowLayout, Spinner, muted_label, set_variant

if TYPE_CHECKING:
    from localwrite.app_controller import AppController


class AssistantPage(QWidget):
    def __init__(self, controller: "AppController") -> None:
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
        lay.setSpacing(18)

        title = QLabel("Writing Assistant")
        title.setObjectName("PageTitle")
        sub = QLabel("Type or paste text, choose a mode and get an instant correction from your local AI. "
                     "Nothing you write here is saved.")
        sub.setObjectName("PageSubtitle")
        sub.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(sub)

        # ---------------- input card (no shadow effect: it hosts an editor)
        card = Card(shadow=False)
        mode_lbl = QLabel("WRITING MODE")
        mode_lbl.setObjectName("SectionLabel")
        card.body.addWidget(mode_lbl)
        chips = QWidget()
        flow = FlowLayout(chips, spacing=8)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons: dict[str, QPushButton] = {}
        for key in MODE_ORDER:
            b = QPushButton(MODES[key].short)
            b.setProperty("chip", True)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(MODES[key].description)
            b.clicked.connect(lambda _=False, k=key: self._mode_changed(k))
            self.mode_group.addButton(b)
            flow.addWidget(b)
            self.mode_buttons[key] = b
        card.body.addWidget(chips)
        self.mode_desc = muted_label(small=True)
        card.body.addWidget(self.mode_desc)
        self.custom = QLineEdit()
        self.custom.setPlaceholderText("Describe what to do, e.g. 'Make it a polite reply to a customer'")
        card.body.addWidget(self.custom)

        self.editor = QPlainTextEdit()
        self.editor.setObjectName("Editor")
        self.editor.setPlaceholderText("Start typing or paste your text here...")
        self.editor.setMinimumHeight(170)
        self.editor.textChanged.connect(self._text_changed)
        card.body.addWidget(self.editor)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.correct_btn = set_variant(QPushButton("  Correct"), "primary")
        self.correct_btn.setIcon(line_icon("sparkle", "#ffffff", 16))
        self.correct_btn.setToolTip("Correct the text (Ctrl+Enter)")
        self.correct_btn.clicked.connect(self._run)
        self.cancel_btn = set_variant(QPushButton("Cancel"), "ghost")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.hide()
        self.spinner = Spinner(16)
        clear = set_variant(QPushButton("Clear"), "ghost")
        clear.clicked.connect(self._clear)
        self.count = muted_label(wrap=False, small=True)
        row.addWidget(self.correct_btn)
        row.addWidget(self.cancel_btn)
        row.addWidget(self.spinner)
        row.addStretch(1)
        row.addWidget(self.count)
        row.addWidget(clear)
        card.body.addLayout(row)
        lay.addWidget(card)
        QShortcut(QKeySequence("Ctrl+Return"), self.editor, activated=self._run)

        # ---------------- result card
        self.result_card = Card(shadow=False)
        rh = QHBoxLayout()
        rlbl = QLabel("SUGGESTION")
        rlbl.setObjectName("SectionLabel")
        self.result_chip = QLabel()
        self.result_chip.setObjectName("ChipAccent")
        self.result_meta = muted_label(wrap=False, small=True)
        self.show_changes = QPushButton("Show changes")
        self.show_changes.setProperty("chip", True)
        self.show_changes.setCheckable(True)
        self.show_changes.setChecked(True)
        self.show_changes.toggled.connect(lambda _c: self._render())
        rh.addWidget(rlbl)
        rh.addWidget(self.result_chip)
        rh.addStretch(1)
        rh.addWidget(self.result_meta)
        rh.addWidget(self.show_changes)
        self.result_card.body.addLayout(rh)
        self.result_view = QTextBrowser()
        self.result_view.setObjectName("ResultView")
        self.result_view.setFrameShape(QFrame.Shape.NoFrame)
        self.result_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.result_card.body.addWidget(self.result_view)
        self.error_label = ErrorBanner()
        self.error_label.hide()
        self.result_card.body.addWidget(self.error_label)
        arow = QHBoxLayout()
        self.copy_btn = set_variant(QPushButton("  Copy corrected text"), "primary")
        self.copy_btn.setIcon(line_icon("clipboard", "#ffffff", 16))
        self.copy_btn.clicked.connect(self._copy)
        self.use_btn = QPushButton("Use as my text")
        self.use_btn.setToolTip("Replace the text above with the suggestion")
        self.use_btn.clicked.connect(self._use)
        self.copied = QLabel()
        self.copied.setStyleSheet(f"color: {p.success}; font-weight: 600;")
        arow.addWidget(self.copy_btn)
        arow.addWidget(self.use_btn)
        arow.addWidget(self.copied)
        arow.addStretch(1)
        self.result_card.body.addLayout(arow)
        self.result_card.hide()
        lay.addWidget(self.result_card)
        lay.addStretch(1)

        self._token = None
        self._result = None
        self._mode = controller.settings.default_mode
        self._select_mode(self._mode)
        self._text_changed()

    # ------------------------------------------------------------------ helpers
    def focus_editor(self) -> None:
        self.editor.setFocus()

    def _select_mode(self, key: str) -> None:
        self._mode = key
        self.mode_buttons[key].setChecked(True)
        self.mode_desc.setText(MODES[key].description)
        self.custom.setVisible(key == "custom")
        if key == "custom" and not self.custom.text():
            self.custom.setText(self.c.settings.custom_instruction)

    def _mode_changed(self, key: str) -> None:
        self._select_mode(key)
        if key == "custom":
            self.custom.setFocus()

    def _text_changed(self) -> None:
        n = len(self.editor.toPlainText())
        words = len(self.editor.toPlainText().split())
        self.count.setText(f"{words} words · {n:,} characters" if n else "")
        self.correct_btn.setEnabled(bool(self.editor.toPlainText().strip()) and self._token is None)

    def _busy(self, busy: bool) -> None:
        self.cancel_btn.setVisible(busy)
        if busy:
            self.spinner.start()
        else:
            self.spinner.stop()
        self.correct_btn.setEnabled(not busy and bool(self.editor.toPlainText().strip()))
        for b in self.mode_buttons.values():
            b.setEnabled(not busy)

    # ------------------------------------------------------------------ actions
    def _run(self) -> None:
        text = self.editor.toPlainText()
        if not text.strip() or self._token is not None:
            return
        instruction = self.custom.text().strip() if self._mode == "custom" else ""
        if self._mode == "custom" and not instruction:
            self.custom.setFocus()
            self.custom.setPlaceholderText("Please describe what LocalWrite should do with your text")
            return
        self._result = None
        self.result_card.show()
        self.result_chip.setText("Working...")
        self.result_chip.setObjectName("ChipAccent")
        self.result_chip.style().unpolish(self.result_chip)
        self.result_chip.style().polish(self.result_chip)
        self.result_meta.setText("")
        self.result_view.setHtml("")
        self.result_view.show()
        self.result_chip.show()
        self.show_changes.show()
        self.error_label.hide()
        self.copied.setText("")
        self.copy_btn.setEnabled(False)
        self.use_btn.setEnabled(False)

        def progress(partial: str) -> None:
            if self._token is not None:
                self.result_view.setHtml(plain_html(partial))
                self._fit_result()

        def done(result, error) -> None:
            self._token = None
            self._busy(False)
            if error is not None:
                if isinstance(error, OllamaCancelledError):
                    self.result_card.hide()
                    return
                # Same error state as the popup and every other screen: just "AI error".
                self.result_chip.hide()
                self.result_view.hide()
                self.show_changes.hide()
                self.error_label.show()
                return
            self._result = result
            self.copy_btn.setEnabled(True)
            self.use_btn.setEnabled(result.changed)
            self._render()

        self._token = self.c.playground_correct(text, self._mode, progress, done, custom_instruction=instruction)
        self._busy(self._token is not None)

    def _render(self) -> None:
        r = self._result
        if r is None:
            return
        ops = compute_diff(r.original, r.corrected)
        n = change_count(ops)
        self.result_chip.setText(f"{n} improvement{'s' if n != 1 else ''}" if n else "Looks good")
        self.result_chip.setObjectName("ChipAccent" if n else "ChipSuccess")
        self.result_chip.style().unpolish(self.result_chip)
        self.result_chip.style().polish(self.result_chip)
        self.result_meta.setText(f"{r.elapsed:.1f}s · {r.model}")
        if self.show_changes.isChecked():
            self.result_view.setHtml(render_inline(ops, theme.current().diff_colors))
        else:
            self.result_view.setHtml(plain_html(r.corrected))
        self._fit_result()

    def _fit_result(self) -> None:
        """Size the suggestion to its content (scrolling beyond ~420px)."""
        doc = self.result_view.document()
        doc.setTextWidth(max(200, self.result_view.viewport().width()))
        self.result_view.setFixedHeight(max(70, min(420, int(doc.size().height()) + 16)))

    def _cancel(self) -> None:
        if self._token is not None:
            self._token.cancel("user")
            self._token = None
            self._busy(False)
            self.result_card.hide()

    def _copy(self) -> None:
        if self._result and self.c.copy_text(self._result.corrected):
            self.copied.setText("✔ Copied")

    def _use(self) -> None:
        if self._result:
            self.editor.setPlainText(self._result.corrected)
            self.result_card.hide()
            self._result = None

    def _clear(self) -> None:
        self._cancel()
        self.editor.clear()
        self.result_card.hide()
        self._result = None
