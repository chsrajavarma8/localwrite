"""Start-with-Windows support (off by default).

Mechanism: one named value under the per-user Run key
(HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run). It needs no admin
rights, can never be duplicated (a value name is unique), and launches
LocalWrite with ``--minimized`` so it starts quietly in the system tray.

Windows also lets users turn startup apps off in Task Manager / Settings >
Apps > Startup. That choice is stored separately under
...\\Explorer\\StartupApproved\\Run; ``is_enabled()`` honours it so the
LocalWrite setting always reflects what will really happen at sign-in.
"""
from __future__ import annotations

import logging
import sys
import winreg
from pathlib import Path

from localwrite import paths

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
VALUE_NAME = "LocalWrite"
# StartupApproved data: first byte 0x02 = enabled; an odd first byte (0x03, 0x07) = disabled by the user.
_APPROVED_ENABLED = bytes([0x02] + [0x00] * 11)


class StartupError(Exception):
    pass


def launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw
    script = paths.project_root() / "launch.pyw"
    return f'"{exe}" "{script}" --minimized'


def registered_command() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return str(value) if value else None
    except OSError:
        return None


def _disabled_in_task_manager() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY) as key:
            data, _ = winreg.QueryValueEx(key, VALUE_NAME)
    except OSError:
        return False
    return bool(isinstance(data, (bytes, bytearray)) and data and data[0] & 0x01)


def is_enabled() -> bool:
    """True only if LocalWrite will actually launch at the next sign-in."""
    return registered_command() is not None and not _disabled_in_task_manager()


def is_current() -> bool:
    """True if the registered command points at this installation."""
    return registered_command() == launch_command()


def set_enabled(enabled: bool) -> None:
    """Create/refresh or remove the startup entry. Raises StartupError on failure."""
    try:
        if enabled:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, launch_command())
            # Re-enabling from LocalWrite also clears a "disabled" flag set in Task Manager.
            if _disabled_in_task_manager():
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY) as key:
                    winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_BINARY, _APPROVED_ENABLED)
            log.info("Start with Windows enabled")
        else:
            for key_path in (RUN_KEY, APPROVED_KEY):
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                        winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
            log.info("Start with Windows disabled")
    except OSError as exc:
        raise StartupError(str(exc)) from exc


def sync(wanted: bool) -> bool:
    """Make the system match the wanted state; return the state actually in effect."""
    try:
        if wanted and not (is_enabled() and is_current()):
            set_enabled(True)  # also repairs an entry pointing at an old location
        elif not wanted and registered_command() is not None:
            set_enabled(False)
    except StartupError:
        log.warning("Could not update the Windows startup entry")
    return is_enabled()
