"""Launch-at-login support through the per-user Run registry key (no admin needed)."""
from __future__ import annotations

import logging
import sys
import winreg
from pathlib import Path

from localwrite import paths

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "LocalWrite"


def launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw
    script = paths.project_root() / "launch.pyw"
    return f'"{exe}" "{script}" --minimized'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, launch_command())
            log.info("Enabled start with Windows")
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
                log.info("Disabled start with Windows")
            except FileNotFoundError:
                pass
