"""Icons drawn in code (crisp at any DPI, no binary assets needed at runtime)."""
from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

_STATES = {
    "normal": ("#5b8cff", "#2a5ae0"),
    "disabled": ("#b4bac5", "#7d8492"),
    "busy": ("#8b7bff", "#5b46e0"),
    "error": ("#ff8a8a", "#d63c3c"),
}


def render_app_icon(size: int, state: str = "normal", live_dot: bool = False) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    m = size * 0.04
    rect = QRectF(m, m, size - 2 * m, size - 2 * m)
    top, bottom = _STATES.get(state, _STATES["normal"])
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0, QColor(top))
    grad.setColorAt(1, QColor(bottom))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(rect, size * 0.26, size * 0.26)

    pen = QPen(QColor("white"))
    pen.setWidthF(max(1.6, size * 0.10))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    path = QPainterPath(QPointF(size * 0.27, size * 0.47))
    path.lineTo(QPointF(size * 0.43, size * 0.62))
    path.lineTo(QPointF(size * 0.74, size * 0.31))
    p.drawPath(path)
    pen.setWidthF(max(1.2, size * 0.065))
    pen.setColor(QColor(255, 255, 255, 165))
    p.setPen(pen)
    p.drawLine(QPointF(size * 0.28, size * 0.77), QPointF(size * 0.72, size * 0.77))

    if live_dot:
        r = size * 0.17
        c = QPointF(size - r - m * 0.5, r + m * 0.5)
        p.setPen(QPen(QColor("white"), max(1.0, size * 0.05)))
        p.setBrush(QColor("#ff9f1a"))
        p.drawEllipse(c, r, r)
    p.end()
    return img


@lru_cache(maxsize=32)
def app_icon(state: str = "normal", live_dot: bool = False) -> QIcon:
    icon = QIcon()
    for s in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(render_app_icon(s, state, live_dot)))
    return icon


# ---------------------------------------------------------------------- line icons
def _draw(name: str, p: QPainter) -> None:
    """Draw a 24x24 line icon (coordinates in a 24-unit grid)."""
    P = QPointF
    if name == "home":
        path = QPainterPath(P(3.5, 11))
        path.lineTo(12, 4)
        path.lineTo(20.5, 11)
        p.drawPath(path)
        body = QPainterPath(P(6, 9.5))
        body.lineTo(6, 20)
        body.lineTo(18, 20)
        body.lineTo(18, 9.5)
        p.drawPath(body)
        door = QPainterPath(P(10, 20))
        door.lineTo(10, 15)
        door.lineTo(14, 15)
        door.lineTo(14, 20)
        p.drawPath(door)
    elif name == "pen":
        path = QPainterPath(P(4, 20))
        path.lineTo(5, 15.5)
        path.lineTo(15, 5.5)
        path.lineTo(18.5, 9)
        path.lineTo(8.5, 19)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(P(13, 7.5), P(16.5, 11))
        p.drawLine(P(19.5, 14.5), P(19.5, 19.5))
        p.drawLine(P(17, 17), P(22, 17))
    elif name == "settings":
        p.drawEllipse(P(12, 12), 3, 3)
        p.drawEllipse(P(12, 12), 6.6, 6.6)
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(P(12 + 6.6 * math.cos(a), 12 + 6.6 * math.sin(a)),
                       P(12 + 9.2 * math.cos(a), 12 + 9.2 * math.sin(a)))
    elif name == "info":
        p.drawEllipse(P(12, 12), 9, 9)
        p.drawLine(P(12, 11), P(12, 16.5))
        p.drawPoint(P(12, 7.8))
    elif name == "check":
        path = QPainterPath(P(5, 12.5))
        path.lineTo(10, 17.5)
        path.lineTo(19, 7)
        p.drawPath(path)
    elif name == "shield":
        path = QPainterPath(P(12, 3))
        path.lineTo(19.5, 6)
        path.lineTo(19.5, 11)
        path.cubicTo(19.5, 16, 16, 19.5, 12, 21)
        path.cubicTo(8, 19.5, 4.5, 16, 4.5, 11)
        path.lineTo(4.5, 6)
        path.closeSubpath()
        p.drawPath(path)
        tick = QPainterPath(P(8.8, 12))
        tick.lineTo(11.2, 14.4)
        tick.lineTo(15.4, 9.6)
        p.drawPath(tick)
    elif name == "bolt":
        path = QPainterPath(P(13.5, 3))
        path.lineTo(5.5, 13.5)
        path.lineTo(11.5, 13.5)
        path.lineTo(10.5, 21)
        path.lineTo(18.5, 10.5)
        path.lineTo(12.5, 10.5)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "keyboard":
        p.drawRoundedRect(QRectF(3, 6.5, 18, 11), 2.5, 2.5)
        for x in (7, 10.3, 13.7, 17):
            p.drawPoint(P(x, 10))
        p.drawLine(P(8, 14), P(16, 14))
    elif name == "server":
        p.drawRoundedRect(QRectF(4, 4.5, 16, 6), 2, 2)
        p.drawRoundedRect(QRectF(4, 13.5, 16, 6), 2, 2)
        p.drawPoint(P(7.5, 7.5))
        p.drawPoint(P(7.5, 16.5))
    elif name == "chip":
        p.drawRoundedRect(QRectF(6.5, 6.5, 11, 11), 2, 2)
        p.drawRoundedRect(QRectF(9.8, 9.8, 4.4, 4.4), 1, 1)
        for v in (9.5, 12, 14.5):
            p.drawLine(P(v, 3.5), P(v, 6.5))
            p.drawLine(P(v, 17.5), P(v, 20.5))
            p.drawLine(P(3.5, v), P(6.5, v))
            p.drawLine(P(17.5, v), P(20.5, v))
    elif name == "sparkle":
        path = QPainterPath(P(12, 3))
        path.cubicTo(12.8, 8.5, 15.5, 11.2, 21, 12)
        path.cubicTo(15.5, 12.8, 12.8, 15.5, 12, 21)
        path.cubicTo(11.2, 15.5, 8.5, 12.8, 3, 12)
        path.cubicTo(8.5, 11.2, 11.2, 8.5, 12, 3)
        p.drawPath(path)
    elif name == "refresh":
        p.drawArc(QRectF(5, 5, 14, 14), 30 * 16, 290 * 16)
        path = QPainterPath(P(19.5, 4.5))
        path.lineTo(19.2, 9.2)
        path.lineTo(14.6, 8.6)
        p.drawPath(path)
    elif name == "lock":
        p.drawRoundedRect(QRectF(5, 10.5, 14, 10), 2.5, 2.5)
        path = QPainterPath(P(8.5, 10.5))
        path.lineTo(8.5, 8)
        path.cubicTo(8.5, 3.5, 15.5, 3.5, 15.5, 8)
        path.lineTo(15.5, 10.5)
        p.drawPath(path)
    elif name == "clipboard":
        p.drawRoundedRect(QRectF(5, 5, 14, 16), 2.5, 2.5)
        p.drawRoundedRect(QRectF(9, 3, 6, 4), 1.5, 1.5)
        p.drawLine(P(8.5, 12), P(15.5, 12))
        p.drawLine(P(8.5, 16), P(13.5, 16))
    elif name == "window":
        p.drawRoundedRect(QRectF(3.5, 5, 17, 14), 2.5, 2.5)
        p.drawLine(P(3.5, 9), P(20.5, 9))
    elif name == "alert":
        path = QPainterPath(P(12, 3.5))
        path.lineTo(21, 19.5)
        path.lineTo(3, 19.5)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(P(12, 9.5), P(12, 14))
        p.drawPoint(P(12, 16.8))


@lru_cache(maxsize=256)
def line_icon(name: str, color: str = "#384152", size: int = 20, stroke: float = 1.7) -> QIcon:
    scale = 3  # supersample for high-DPI displays
    px = size * scale
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(px / 24.0, px / 24.0)
    pen = QPen(QColor(color), stroke)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    _draw(name, p)
    p.end()
    pm.setDevicePixelRatio(scale)
    return QIcon(pm)


def line_pixmap(name: str, color: str = "#384152", size: int = 20) -> QPixmap:
    return line_icon(name, color, size).pixmap(size, size)


def write_ico(path: str, sizes=(16, 24, 32, 48, 64, 128, 256)) -> None:
    """Write a multi-resolution .ico (PNG-compressed entries) for PyInstaller/shortcuts."""
    import struct

    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    blobs = []
    for s in sizes:
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        render_app_icon(s).save(buf, "PNG")
        blobs.append((s, bytes(ba.data())))
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries = b""
    data = b""
    for s, blob in blobs:
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(blob), offset + len(data))
        data += blob
    with open(path, "wb") as fh:
        fh.write(header + entries + data)
