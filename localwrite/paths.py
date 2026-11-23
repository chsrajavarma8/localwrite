r"""Filesystem locations used by the application.

All user data lives under %APPDATA%\LocalWrite (or LOCALWRITE_HOME when set,
which the test-suite uses to isolate itself from the real profile).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "LocalWrite"


def data_dir() -> Path:
    override = os.environ.get("LOCALWRITE_HOME")
    if override:
        path = Path(override)
    else:
        base = os.environ.get("APPDATA") or str(Path.home())
        path = Path(base) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file() -> Path:
    return data_dir() / "settings.json"


def purge_legacy_history() -> int:
    """Delete correction-history files left by earlier versions. Returns the number removed.

    LocalWrite no longer stores any text; this makes sure nothing old lingers on disk.
    """
    removed = 0
    for name in ("history.db", "history.db-wal", "history.db-shm", "history.db-journal"):
        path = data_dir() / name
        try:
            if path.exists():
                path.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_root() -> Path:
    """Root folder containing resources (handles PyInstaller one-file bundles)."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle)
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    return project_root().joinpath("resources", *parts)
