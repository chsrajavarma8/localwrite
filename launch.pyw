"""Double-clickable launcher (runs without a console window via pythonw)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from localwrite.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
