"""A stand-in 'other application' for desktop tests.

Usage: target_app.py <initial-text-file> <output-file>
Shows a text editor with all text selected, prints its HWND, and mirrors the
editor contents to <output-file> whenever they change.
"""
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPlainTextEdit


def main() -> int:
    initial = Path(sys.argv[1]).read_text(encoding="utf-8")
    out = Path(sys.argv[2])
    app = QApplication(sys.argv)
    ed = QPlainTextEdit()
    ed.setWindowTitle("LocalWrite test target")
    ed.setPlainText(initial)
    ed.resize(500, 200)
    ed.textChanged.connect(lambda: out.write_text(ed.toPlainText(), encoding="utf-8"))
    ed.show()
    ed.selectAll()
    ed.raise_()
    ed.activateWindow()
    ed.setFocus()
    out.write_text(ed.toPlainText(), encoding="utf-8")
    print(int(ed.winId()), flush=True)
    QTimer.singleShot(60_000, app.quit)  # safety net
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
