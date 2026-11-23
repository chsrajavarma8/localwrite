"""Reusable widgets for the LocalWrite design system."""
from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPoint, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLayout, QSizePolicy, QVBoxLayout,
    QWidget,
)

from localwrite.ui import theme
from localwrite.ui.icons import line_pixmap


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)


def set_variant(button, variant: str):
    button.setProperty("variant", variant)
    repolish(button)
    return button


def muted_label(text: str = "", wrap: bool = True, small: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("muted", True)
    if small:
        lbl.setProperty("small", True)
    lbl.setWordWrap(wrap)
    return lbl


def soft_shadow(widget: QWidget, blur: int = 26, dy: int = 3, alpha: int = 16) -> None:
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(16, 24, 40, alpha))
    widget.setGraphicsEffect(eff)


def icon_label(name: str, color: str | None = None, size: int = 18) -> QLabel:
    lbl = QLabel()
    lbl.setPixmap(line_pixmap(name, color or theme.current().text_soft, size))
    lbl.setFixedSize(size + 2, size + 2)
    return lbl


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFrameShape(QFrame.Shape.NoFrame)
    return line


class Card(QFrame):
    """White rounded card with an optional icon + title header and a soft shadow."""

    def __init__(self, title: str = "", icon: str = "", subtitle: str = "", shadow: bool = True,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(20, 18, 20, 18)
        self.body.setSpacing(10)
        self.header = None
        if title:
            self.header = QHBoxLayout()
            self.header.setSpacing(9)
            if icon:
                self.header.addWidget(icon_label(icon, theme.current().accent, 18))
            t = QLabel(title)
            t.setObjectName("CardTitle")
            self.header.addWidget(t)
            self.header.addStretch(1)
            self.body.addLayout(self.header)
            if subtitle:
                self.body.addWidget(muted_label(subtitle))
        if shadow:
            soft_shadow(self)


class StatusPill(QWidget):
    """A coloured dot followed by text, e.g. ● Connected."""

    def __init__(self, text: str = "", state: str = "unknown", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(7)
        self.dot = QLabel()
        self.dot.setFixedSize(9, 9)
        self.label = QLabel(text)
        self.label.setStyleSheet("font-weight: 600;")
        lay.addWidget(self.dot)
        lay.addWidget(self.label)
        lay.addStretch(1)
        self.set_state(state, text)

    def set_state(self, state: str, text: str | None = None) -> None:
        p = theme.current()
        color = {"ok": p.success, "warn": p.warning, "error": p.danger, "busy": p.accent}.get(state, "#b4bac5")
        self.dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        if text is not None:
            self.label.setText(text)


class KeyCap(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text or "-", parent)
        self.setObjectName("KeyCap")


def keycaps_row(combo: str) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    if not combo:
        lay.addWidget(muted_label("Not set", wrap=False))
    else:
        for part in combo.split("+"):
            lay.addWidget(KeyCap(part))
    lay.addStretch(1)
    return w


class Spinner(QWidget):
    def __init__(self, size: int = 18, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def start(self) -> None:
        self._timer.start()
        self.show()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._angle = (self._angle + 7) % 360
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(2, 2, self.width() - 4, self.height() - 4)
        track = QPen(QColor(theme.current().border), 2.2)
        p.setPen(track)
        p.drawEllipse(r)
        pen = QPen(QColor(theme.current().accent), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(r, -self._angle * 16, 100 * 16)


class ToggleSwitch(QAbstractButton):
    """An animated on/off switch."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(40, 22)

    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, v: float) -> None:
        self._pos = v
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        super().setChecked(checked)
        self._anim.stop()
        self._pos = 1.0 if checked else 0.0
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = theme.current()
        on = QColor(pal.accent)
        off = QColor("#d3d8e0")
        t = self._pos
        track = QColor(
            int(off.red() + (on.red() - off.red()) * t),
            int(off.green() + (on.green() - off.green()) * t),
            int(off.blue() + (on.blue() - off.blue()) * t),
        )
        if not self.isEnabled():
            track.setAlpha(110)
        h = self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, self.width(), h), h / 2, h / 2)
        d = h - 6
        x = 3 + t * (self.width() - d - 6)
        p.setBrush(QColor(0, 0, 0, 25))
        p.drawEllipse(QRectF(x, 3.6, d, d))
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, 3, d, d))


class SettingRow(QWidget):
    """Title + description on the left, a control on the right (or below when stacked)."""

    def __init__(self, title: str, description: str = "", control: QWidget | None = None,
                 stacked: bool = False, control_width: int | None = None) -> None:
        super().__init__()
        outer = QVBoxLayout(self) if stacked else QHBoxLayout(self)
        outer.setContentsMargins(0, 10, 0, 10)
        outer.setSpacing(8 if stacked else 20)
        text = QVBoxLayout()
        text.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("RowTitle")
        text.addWidget(t)
        if description:
            text.addWidget(muted_label(description, small=True))
        outer.addLayout(text, 1)
        if control is not None:
            if control_width:
                control.setFixedWidth(control_width)
            if stacked:
                outer.addWidget(control)
            else:
                outer.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)


class ModeTile(QFrame):
    """A selectable tile showing a writing mode's name and description."""

    clicked = Signal(str)

    def __init__(self, key: str, title: str, description: str) -> None:
        super().__init__()
        self.key = key
        self.setProperty("tile", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(3)
        t = QLabel(title)
        t.setStyleSheet("font-weight: 700; background: transparent;")
        d = muted_label(description, small=True)
        d.setStyleSheet("background: transparent;")
        lay.addWidget(t)
        lay.addWidget(d)
        lay.addStretch(1)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        repolish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)


class FlowLayout(QLayout):
    """Lays out child widgets left-to-right, wrapping onto new lines (for chips)."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._arrange(QRect(0, 0, width, 0), test=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._arrange(rect, test=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _arrange(self, rect: QRect, test: bool) -> int:
        x, y, line_h = rect.x(), rect.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > rect.right() + 1 and line_h > 0:
                x = rect.x()
                y += line_h + self._spacing
                line_h = 0
            if not test:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()
