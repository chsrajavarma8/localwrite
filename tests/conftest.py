import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Isolate every test run from the real %APPDATA%\LocalWrite profile.
os.environ["LOCALWRITE_HOME"] = tempfile.mkdtemp(prefix="localwrite-test-")


def pytest_configure(config):
    config.addinivalue_line("markers", "desktop: drives real windows, keyboard and clipboard (run on an unlocked desktop)")
    config.addinivalue_line("markers", "ollama: needs a running Ollama server with a model installed")


def pytest_collection_modifyitems(config, items):
    run_desktop = os.environ.get("LOCALWRITE_DESKTOP_TESTS") == "1"
    run_ollama = os.environ.get("LOCALWRITE_OLLAMA_TESTS") == "1"
    for item in items:
        if "desktop" in item.keywords and not run_desktop:
            item.add_marker(pytest.mark.skip(reason="set LOCALWRITE_DESKTOP_TESTS=1 to run desktop tests"))
        if "ollama" in item.keywords and not run_ollama:
            item.add_marker(pytest.mark.skip(reason="set LOCALWRITE_OLLAMA_TESTS=1 to run Ollama tests"))
