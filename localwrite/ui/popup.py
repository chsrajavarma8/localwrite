"""The floating correction popup.

It never takes keyboard focus (WS_EX_NOACTIVATE via Qt.WindowDoesNotAcceptFocus),
so the user's selection in the original app stays intact while they read and
click. Escape is handled by a temporary global hotkey while it is visible.
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QMenu, QPushButton, QSizeGrip, QSizePolicy, QTextBrowser,
    QToolButton, QVBoxLayout, QWidget,
)

from localwrite.core.diff import DiffOp, plain_html, render_side
from localwrite.core.modes import MODE_ORDER, MODES
from localwrite.ui import theme
from localwrite.ui.icons import app_icon, line_icon, line_pixmap
from localwrite.ui.widgets import Spinner, muted_label, set_variant

DEFAULT_WIDTH = 600
MIN_WIDTH = 460


def compute_position(anchor: QPoint, size: QSize, avail: QRect, mode: str) -> QPoint:
    """Pick the popup's top-left so it is fully visible and close to (but not over) the anchor."""
    margin = 12
    w, h = size.width(), size.height()
    if mode == "center":
        x = avail.center().x() - w // 2
        y = avail.center().y() - h // 2
    elif mode == "top_right":
        x, y = avail.right() - w - margin, avail.top() + margin
    elif mode == "bottom_right":
        x, y = avail.right() - w - margin, avail.bottom() - h - margin
    else:  # near the caret / cursor: prefer below so the text being corrected stays visible
        x = anchor.x() - 60
        y = anchor.y() + 22
        if y + h > avail.bottom() - margin:
            y = anchor.y() - h - 22
    x = max(avail.left() + margin, min(x, avail.right() - w - margin))
    y = max(avail.top() + margin, min(y, avail.bottom() - h - margin))
    return QPoint(x, y)


class DiffView(QTextBrowser):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DiffView")
        self.setReadOnly(True)
        self.setOpenLinks(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def content_height(self, width: int) -> int:
        doc = self.document()
        doc.setTextWidth(max(100, width - 20))
        return int(doc.size().height()) + 18

    def fit(self, width: int, max_height: int) -> None:
        self.setFixedHeight(max(44, min(max_height, self.content_height(width))))

    def free(self) -> None:
        self.setMinimumHeight(44)
        self.setMaximumHeight(16777215)


class _Grip(QSizeGrip):
    """Size grip that tells the popup the user has taken control of its size."""

    def __init__(self, popup: "CorrectionPopup") -> None:
        super().__init__(popup)
        self._popup = popup
        self.setToolTip("Drag to resize")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._popup.enter_manual_size()
        super().mousePressEvent(event)


class CorrectionPopup(QWidget):
    accept_clicked = Signal()
    copy_clicked = Signal()
    retry_clicked = Signal()
    cancel_clicked = Signal()
    close_clicked = Signal()
    mode_selected = Signal(str)
    visibility_changed = Signal(bool)

    def __init__(self) -> None:
        flags = (
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMinimumWidth(MIN_WIDTH)
        self.resize(DEFAULT_WIDTH, 300)
        self.setWindowTitle("LocalWrite suggestion")
        self._drag_origin: QPoint | None = None
        self._manual_size = False
        p = theme.current()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 14, 20, 24)
        self.frame = QFrame()
        self.frame.setObjectName("PopupFrame")
        shadow = QGraphicsDropShadowEffect(self.frame)
        shadow.setBlurRadius(42)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(15, 23, 42, 46))
        self.frame.setGraphicsEffect(shadow)
        outer.addWidget(self.frame)

        lay = QVBoxLayout(self.frame)
        lay.setContentsMargins(18, 14, 18, 12)
        lay.setSpacing(8)

        # Header (also the drag handle)
        self.header = QWidget()
        self.header.setCursor(Qt.CursorShape.SizeAllCursor)
        hdr = QHBoxLayout(self.header)
        hdr.setContentsMargins(0, 0, 0, 2)
        hdr.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(app_icon().pixmap(20, 20))
        self.title = QLabel("LocalWrite")
        self.title.setObjectName("PopupTitle")
        self.source_label = muted_label(wrap=False, small=True)
        self.mode_chip = QLabel()
        self.mode_chip.setObjectName("ChipAccent")
        self.model_chip = QLabel()
        self.model_chip.setObjectName("Chip")
        for chip in (self.mode_chip, self.model_chip):
            chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        close_btn = QToolButton()
        close_btn.setObjectName("CloseButton")
        close_btn.setText("✕")
        close_btn.setToolTip("Close (Esc)")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.close_clicked.emit)
        hdr.addWidget(icon)
        hdr.addWidget(self.title)
        hdr.addWidget(self.source_label)
        hdr.addSpacing(4)
        hdr.addWidget(self.mode_chip)
        hdr.addStretch(1)
        self.model_chip.hide()  # the model name is not shown in the popup
        hdr.addWidget(close_btn)
        lay.addWidget(self.header)

        # Loading / working status
        self.status_row = QWidget()
        st = QHBoxLayout(self.status_row)
        st.setContentsMargins(0, 0, 0, 0)
        st.setSpacing(9)
        self.spinner = Spinner(16)
        self.status_label = QLabel("Working...")
        self.status_label.setStyleSheet(f"color: {p.text_soft};")
        self.cancel_btn = set_variant(QPushButton("Cancel"), "ghost")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.cancel_clicked.emit)
        st.addWidget(self.spinner)
        st.addWidget(self.status_label)
        st.addStretch(1)
        st.addWidget(self.cancel_btn)
        lay.addWidget(self.status_row)

        # Original
        self.original_label = QLabel("ORIGINAL")
        self.original_label.setObjectName("SectionLabel")
        self.original_view = DiffView()
        lay.addWidget(self.original_label)
        lay.addWidget(self.original_view, 2)

        # Suggestion
        self.corrected_header = QWidget()
        ch = QHBoxLayout(self.corrected_header)
        ch.setContentsMargins(0, 4, 0, 0)
        lbl = QLabel("SUGGESTION")
        lbl.setObjectName("SectionLabel")
        self.changes_chip = QLabel()
        self.changes_chip.setObjectName("Chip")
        ch.addWidget(lbl)
        ch.addStretch(1)
        ch.addWidget(self.changes_chip)
        self.corrected_view = DiffView()
        lay.addWidget(self.corrected_header)
        lay.addWidget(self.corrected_view, 3)

        # Friendly error panel (technical details hidden behind a toggle)
        self.error_panel = QFrame()
        self.error_panel.setObjectName("NoticeError")
        ep = QHBoxLayout(self.error_panel)
        ep.setContentsMargins(14, 12, 14, 12)
        ep.setSpacing(12)
        alert = QLabel()
        alert.setPixmap(line_pixmap("alert", p.danger, 20))
        alert.setAlignment(Qt.AlignmentFlag.AlignTop)
        ep.addWidget(alert, 0, Qt.AlignmentFlag.AlignTop)
        etext = QVBoxLayout()
        etext.setSpacing(4)
        self.error_title = QLabel()
        self.error_title.setObjectName("ErrorTitle")
        self.error_title.setWordWrap(True)
        self.error_hint = QLabel()
        self.error_hint.setWordWrap(True)
        self.error_hint.setStyleSheet(f"color: {p.text_soft};")
        self.error_hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details_btn = set_variant(QPushButton("Show technical details"), "link")
        self.details_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.details_btn.clicked.connect(self._toggle_details)
        self.error_detail = muted_label(small=True)
        self.error_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        for wdg in (self.error_title, self.error_hint, self.details_btn, self.error_detail):
            etext.addWidget(wdg)
        ep.addLayout(etext, 1)
        lay.addWidget(self.error_panel)

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        lay.addWidget(self.info_label)

        # Actions
        btns = QHBoxLayout()
        btns.setContentsMargins(0, 4, 0, 0)
        btns.setSpacing(8)
        self.accept_btn = set_variant(QPushButton("  Accept && Replace"), "primary")
        self.accept_btn.setIcon(line_icon("check", "#ffffff", 16, 2.2))
        self.accept_btn.setToolTip("Replace the selected text in the original app")
        self.copy_btn = QPushButton("  Copy")
        self.copy_btn.setIcon(line_icon("clipboard", p.text_soft, 16))
        self.copy_btn.setToolTip("Copy the corrected text")
        self.retry_btn = QPushButton("  Retry")
        self.retry_btn.setIcon(line_icon("refresh", p.text_soft, 16))
        self.retry_btn.setToolTip("Ask for another version")
        self.mode_btn = QToolButton()
        self.mode_btn.setText("Mode  ▾")
        self.mode_btn.setToolTip("Choose another writing mode")
        self.mode_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.mode_menu = QMenu(self.mode_btn)
        self._mode_group = QActionGroup(self.mode_menu)
        self._mode_actions: dict[str, QAction] = {}
        for key in MODE_ORDER:
            mode = MODES[key]
            act = QAction(mode.label + ("..." if key == "custom" else ""), self.mode_menu)
            act.setToolTip(mode.description)
            act.setCheckable(True)
            act.triggered.connect(lambda _=False, k=key: self.mode_selected.emit(k))
            self._mode_group.addAction(act)
            self.mode_menu.addAction(act)
            self._mode_actions[key] = act
        self.mode_btn.setMenu(self.mode_menu)
        for b in (self.accept_btn, self.copy_btn, self.retry_btn, self.mode_btn):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.accept_btn.clicked.connect(self.accept_clicked.emit)
        self.copy_btn.clicked.connect(self.copy_clicked.emit)
        self.retry_btn.clicked.connect(self.retry_clicked.emit)
        btns.addWidget(self.accept_btn)
        btns.addWidget(self.copy_btn)
        btns.addWidget(self.retry_btn)
        btns.addWidget(self.mode_btn)
        btns.addStretch(1)
        lay.addLayout(btns)

        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        self.hint_label = muted_label("Press Esc to close · drag the header to move", wrap=False, small=True)
        grip_row.addWidget(self.hint_label)
        grip_row.addStretch(1)
        self.grip = _Grip(self)
        grip_row.addWidget(self.grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        lay.addLayout(grip_row)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(150)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._can_replace = True
        self.show_info("")
        self.error_panel.hide()

    # ------------------------------------------------------------------ states
    def set_context(self, mode_key: str, model: str, can_replace: bool, source_note: str = "") -> None:
        mode = MODES.get(mode_key)
        self.mode_chip.setText(mode.label if mode else mode_key)
        self.model_chip.setText(model or "no model")
        self.model_chip.setToolTip(f"Local model: {model}")
        self.source_label.setText(f"· {source_note}" if source_note else "")
        if mode_key in self._mode_actions:
            self._mode_actions[mode_key].setChecked(True)
        self._can_replace = can_replace
        self.accept_btn.setVisible(can_replace)

    def show_loading(self, original: str, status: str) -> None:
        self.original_view.setHtml(plain_html(original))
        self.corrected_view.setHtml("")
        self.changes_chip.setText("")
        self.changes_chip.setObjectName("Chip")
        self._repolish(self.changes_chip)
        self._set_status(status, cancellable=True)
        self.error_panel.hide()
        for w in (self.original_label, self.original_view, self.corrected_header, self.corrected_view):
            w.show()
        self.show_info("")
        self._enable_actions(False, mode=True)
        self._relayout()

    def update_stream(self, partial: str) -> None:
        self.corrected_view.setPlainText(partial)
        bar = self.corrected_view.verticalScrollBar()
        bar.setValue(bar.maximum())
        self._relayout()

    def show_result(self, ops: list[DiffOp], changes: int) -> None:
        colors = theme.current().diff_colors
        self.original_view.setHtml(render_side(ops, "original", colors))
        self.corrected_view.setHtml(render_side(ops, "corrected", colors))
        if changes:
            self.changes_chip.setText(f"{changes} improvement{'s' if changes != 1 else ''}")
            self.changes_chip.setObjectName("ChipAccent")
        else:
            self.changes_chip.setText("Looks good")
            self.changes_chip.setObjectName("ChipSuccess")
        self._repolish(self.changes_chip)
        self.status_row.hide()
        self.spinner.stop()
        self.error_panel.hide()
        self.corrected_header.show()
        self.corrected_view.show()
        self._enable_actions(True, mode=True)
        self.accept_btn.setEnabled(self._can_replace and changes > 0)
        if not changes:
            self.show_info("No changes needed - your text already reads well for this mode.", "ok")
        self._relayout()

    def show_error(self, title: str, detail: str = "", hint: str = "", *, has_original: bool = True,
                   retry: bool = True) -> None:
        self.status_row.hide()
        self.spinner.stop()
        # Errors are shown as a short title only: no hints and no technical details.
        self.error_title.setText(title)
        self.error_hint.hide()
        self.error_detail.hide()
        self.details_btn.hide()
        self.error_panel.show()
        self.corrected_header.hide()
        self.corrected_view.hide()
        self.original_label.setVisible(has_original)
        self.original_view.setVisible(has_original)
        self.show_info("")
        self._enable_actions(False, mode=has_original)
        self.retry_btn.setEnabled(retry and has_original)
        self.accept_btn.setVisible(self._can_replace and has_original)
        self._relayout()

    def set_busy(self, status: str) -> None:
        self._set_status(status, cancellable=False)
        self._enable_actions(False, mode=False)
        self._relayout()

    def show_info(self, text: str, kind: str = "ok") -> None:
        self.info_label.setObjectName({"ok": "InfoOk", "warn": "InfoWarn", "err": "InfoErr"}.get(kind, "InfoOk"))
        self._repolish(self.info_label)
        self.info_label.setText(text)
        self.info_label.setVisible(bool(text))
        if self.isVisible():
            self._relayout()

    def end_busy(self) -> None:
        self.status_row.hide()
        self.spinner.stop()
        self._enable_actions(True, mode=True)

    def _toggle_details(self) -> None:
        show = not self.error_detail.isVisible()
        self.error_detail.setVisible(show)
        self.details_btn.setText("Hide technical details" if show else "Show technical details")
        self._relayout()

    def _set_status(self, text: str, cancellable: bool) -> None:
        self.status_label.setText(text)
        self.cancel_btn.setVisible(cancellable)
        self.status_row.show()
        self.spinner.start()

    def _enable_actions(self, enabled: bool, mode: bool) -> None:
        self.accept_btn.setEnabled(enabled and self._can_replace)
        self.copy_btn.setEnabled(enabled)
        self.retry_btn.setEnabled(enabled)
        self.mode_btn.setEnabled(mode)

    @staticmethod
    def _repolish(w: QWidget) -> None:
        w.style().unpolish(w)
        w.style().polish(w)

    # ------------------------------------------------------------------ geometry
    def enter_manual_size(self) -> None:
        """The user is resizing: let the text areas stretch and scroll instead of auto-fitting."""
        if not self._manual_size:
            self._manual_size = True
            self.original_view.free()
            self.corrected_view.free()

    def _avail(self) -> QRect:
        screen = QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def _relayout(self) -> None:
        if self._manual_size:
            return
        avail = self._avail()
        width = self.width() - 40 - 36
        # Long text scrolls inside each section; the popup never grows past ~80% of the screen.
        self.original_view.fit(width, max(90, int(avail.height() * 0.26)))
        self.corrected_view.fit(width, max(120, int(avail.height() * 0.34)))
        self.frame.layout().activate()
        self.layout().activate()
        width_needed = max(self.width(), self.layout().minimumSize().width())
        self.resize(width_needed, self.layout().sizeHint().height())
        if self.isVisible():
            self._keep_on_screen()

    def show_near(self, anchor: QPoint, position_mode: str) -> None:
        self._manual_size = False
        self.resize(DEFAULT_WIDTH, self.height())
        self._relayout()
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        pos = compute_position(anchor, self.size(), screen.availableGeometry(), position_mode)
        self.move(pos)
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
            self._fade.stop()
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
        self.raise_()
        self._relayout()

    def _keep_on_screen(self) -> None:
        avail = self._avail()
        g = self.frameGeometry()
        x = max(avail.left(), min(g.x(), avail.right() - g.width()))
        y = max(avail.top(), min(g.y(), avail.bottom() - g.height()))
        if (x, y) != (g.x(), g.y()):
            self.move(x, y)

    # ------------------------------------------------------------------ events
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.visibility_changed.emit(True)

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self.spinner.stop()
        self.visibility_changed.emit(False)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.header.geometry().contains(
            self.frame.mapFrom(self, event.position().toPoint())
        ):
            self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_origin = None
        super().mouseReleaseEvent(event)


def anchor_for(caret_physical: tuple[int, int] | None, position_mode: str) -> QPoint:
    """Translate the caret (physical pixels) or mouse cursor into a Qt logical point."""
    if position_mode == "smart" and caret_physical is not None:
        pt = physical_to_logical(*caret_physical)
        if pt is not None:
            return pt
    return QCursor.pos()


def physical_to_logical(x: int, y: int) -> QPoint | None:
    """Qt keeps each screen's native top-left and scales its size by the DPR."""
    for screen in QGuiApplication.screens():
        g = screen.geometry()
        dpr = screen.devicePixelRatio()
        if g.x() <= x < g.x() + g.width() * dpr and g.y() <= y < g.y() + g.height() * dpr:
            return QPoint(int(g.x() + (x - g.x()) / dpr), int(g.y() + (y - g.y()) / dpr))
    return None
