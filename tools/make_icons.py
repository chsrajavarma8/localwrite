"""Generate resources/icons/app.ico and app.png from the code-drawn icon."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from localwrite.ui.icons import render_app_icon, write_ico  # noqa: E402


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 - needed for QImage/QPainter
    out = ROOT / "resources" / "icons"
    out.mkdir(parents=True, exist_ok=True)
    write_ico(str(out / "app.ico"))
    render_app_icon(256).save(str(out / "app.png"))
    print(f"Wrote {out / 'app.ico'} and {out / 'app.png'}")


if __name__ == "__main__":
    main()
