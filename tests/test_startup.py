"""Start-with-Windows: tested against a sandbox registry key, never the real Run key."""
import winreg

import pytest

from localwrite.config.settings import Settings
from localwrite.win import startup

SANDBOX = r"Software\LocalWriteTests"


def _delete_tree(path: str) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(path + "\\" + child)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        pass


@pytest.fixture
def sandbox(monkeypatch):
    monkeypatch.setattr(startup, "RUN_KEY", SANDBOX + r"\Run")
    monkeypatch.setattr(startup, "APPROVED_KEY", SANDBOX + r"\StartupApproved\Run")
    _delete_tree(SANDBOX)
    yield
    _delete_tree(SANDBOX)


def _value_names(path: str) -> list[str]:
    names = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            i = 0
            while True:
                try:
                    names.append(winreg.EnumValue(key, i)[0])
                except OSError:
                    break
                i += 1
    except FileNotFoundError:
        pass
    return names


def test_default_is_off():
    assert Settings().validated().start_with_windows is False


def test_enable_disable_and_no_duplicates(sandbox):
    assert not startup.is_enabled()
    startup.set_enabled(True)
    startup.set_enabled(True)  # enabling twice must not create a second entry
    assert _value_names(startup.RUN_KEY) == ["LocalWrite"]
    assert startup.is_enabled() and startup.is_current()
    assert startup.registered_command().endswith("--minimized")  # starts quietly in the tray
    startup.set_enabled(False)
    assert not startup.is_enabled()
    assert _value_names(startup.RUN_KEY) == []
    startup.set_enabled(False)  # disabling when already off is harmless


def test_task_manager_disable_is_respected(sandbox):
    startup.set_enabled(True)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, startup.APPROVED_KEY) as key:
        winreg.SetValueEx(key, "LocalWrite", 0, winreg.REG_BINARY, bytes([0x03] + [0] * 11))
    assert startup.registered_command() is not None
    assert not startup.is_enabled()  # disabled in Task Manager -> the setting must show off
    assert startup.sync(True) is True  # explicitly enabling from LocalWrite clears the flag
    assert startup.is_enabled()


def test_sync_repairs_stale_path(sandbox):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, startup.RUN_KEY) as key:
        winreg.SetValueEx(key, "LocalWrite", 0, winreg.REG_SZ, r'"C:\old\place\pythonw.exe" x.pyw --minimized')
    assert not startup.is_current()
    assert startup.sync(True)
    assert startup.is_current()
    assert startup.sync(False) is False
    assert startup.registered_command() is None


def test_controller_reflects_actual_state(sandbox, tmp_path, monkeypatch):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from localwrite import app_controller as ac
    from localwrite.config.settings import SettingsStore

    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("LOCALWRITE_HOME", str(tmp_path))
    store = SettingsStore(tmp_path / "settings.json")
    store.save(Settings(model="m", first_run_complete=True, start_with_windows=True))
    c = ac.AppController(app, store)
    # Setting says on, but the user disabled LocalWrite in Task Manager:
    startup.set_enabled(True)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, startup.APPROVED_KEY) as key:
        winreg.SetValueEx(key, "LocalWrite", 0, winreg.REG_BINARY, bytes([0x03] + [0] * 11))
    c._startup_initial_sync()
    assert c.settings.start_with_windows is False
    assert store.load().start_with_windows is False
    # Turning it on from Settings really enables it; turning it off removes the entry.
    c.apply_settings(c.settings.copy(start_with_windows=True))
    assert startup.is_enabled() and c.settings.start_with_windows
    c.apply_settings(c.settings.copy(start_with_windows=False))
    assert startup.registered_command() is None and not c.settings.start_with_windows
    # Off by default: a leftover entry is removed at launch when the setting is off.
    startup.set_enabled(True)
    c._startup_initial_sync()
    assert startup.registered_command() is None
    c.popup.hide()
