"""Optional real-time spelling assistance (disabled by default).

Polls the focused control on a timer - no keyboard hooks. Only standard Win32
edit controls are read (see win.text_fields for the safety rules). When the
user pauses typing, the field's text is checked with the 'quick' mode and a
small clickable badge appears if there are suggestions.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import QLabel, QWidget, QHBoxLayout

from localwrite.core.cancel import CancelToken
from localwrite.core.diff import change_count, compute_diff
from localwrite.ui.invoker import run_background
from localwrite.ui.popup import physical_to_logical
from localwrite.win.text_fields import TextField, focused_text_field, read_field_text

if TYPE_CHECKING:
    from localwrite.app_controller import AppController

log = logging.getLogger(__name__)

POLL_MS = 1200
MIN_CHARS = 4


class SuggestionBadge(QWidget):
    clicked = Signal()

    def __init__(self) -> None:
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setObjectName("Badge")
        self.label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.label.setToolTip("LocalWrite found possible spelling mistakes - click to review")
        lay.addWidget(self.label)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def show_for(self, field: TextField, count: int) -> None:
        self.label.setText(f"✎ {count} spelling fix{'es' if count != 1 else ''}")
        self.adjustSize()
        right, bottom = field.rect[2], field.rect[3]
        pt = physical_to_logical(right, bottom) or QPoint(right, bottom)
        self.move(pt.x() - self.width() - 12, pt.y() - self.height() - 10)
        self.show()
        self.raise_()


class RealtimeAssistant(QObject):
    def __init__(self, controller: "AppController") -> None:
        super().__init__()
        self.c = controller
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self._tick)
        self.badge = SuggestionBadge()
        self.badge.clicked.connect(self._open)
        self._field_hwnd = 0
        self._last_text: str | None = None
        self._stable_ticks = 0
        self._checked_text: str | None = None
        self._inflight: CancelToken | None = None
        self._suggestion: tuple[TextField, str, str] | None = None
        self._count = 0

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.timer.start()
        else:
            self.timer.stop()
            self._reset()

    def _reset(self) -> None:
        self.badge.hide()
        self._suggestion = None
        self._last_text = None
        self._checked_text = None
        self._stable_ticks = 0
        if self._inflight:
            self._inflight.cancel()
            self._inflight = None

    def _tick(self) -> None:
        s = self.c.settings
        if not (s.assistant_enabled and s.realtime_enabled and s.model) or self.c.popup.isVisible():
            self.badge.hide()
            return
        try:
            field = focused_text_field(set(s.realtime_excluded_apps))
            text = read_field_text(field.hwnd) if field else None
        except OSError:
            field, text = None, None
        if field is None or text is None or len(text.strip()) < MIN_CHARS:
            if not self.badge.underMouse():
                self.badge.hide()
            self._field_hwnd = 0
            return
        if field.hwnd != self._field_hwnd or text != self._last_text:
            # The user is typing: wait for a pause and drop stale suggestions.
            self._field_hwnd = field.hwnd
            self._last_text = text
            self._stable_ticks = 0
            if self._suggestion and self._suggestion[1] != text:
                self._suggestion = None
                self.badge.hide()
            return
        self._stable_ticks += 1
        if self._suggestion and self._suggestion[1] == text:
            self.badge.show_for(field, self._count)
            return
        if text == self._checked_text or self._inflight is not None:
            return
        self._check(field, text)

    def _check(self, field: TextField, text: str) -> None:
        token = CancelToken()
        self._inflight = token
        engine = self.c.make_engine()

        def work():
            return engine.correct(text, "quick", cancel=token)

        def done(result) -> None:
            self._inflight = None
            self._checked_text = text
            if token.cancelled or self._last_text != text:
                return
            ops = compute_diff(result.original, result.corrected)
            n = change_count(ops)
            if n and result.changed:
                self._suggestion = (field, text, result.corrected)
                self._count = n
                self.badge.show_for(field, n)
            log.debug("Real-time check finished")

        def failed(exc) -> None:
            self._inflight = None
            self._checked_text = text
            log.info("Real-time check failed: %s", type(exc).__name__)

        run_background(self.c.invoker, work, done, failed, name="LocalWriteRealtime")

    def _open(self) -> None:
        if not self._suggestion:
            return
        field, original, corrected = self._suggestion
        current = read_field_text(field.hwnd)
        self.badge.hide()
        if current != original:
            self._suggestion = None
            return
        self.c.open_realtime_suggestion(field, original, corrected)
        self._suggestion = None
