import pytest

from localwrite.win import winapi as w
from localwrite.win.hotkeys import HotkeyParseError, normalize_hotkey, parse_hotkey, validate_global_hotkey


def test_parse_defaults():
    assert parse_hotkey("Ctrl+Alt+G") == (w.MOD_CONTROL | w.MOD_ALT, ord("G"))
    assert parse_hotkey("ctrl+shift+f5") == (w.MOD_CONTROL | w.MOD_SHIFT, 0x74)
    assert parse_hotkey("Meta+Space") == (w.MOD_WIN, 0x20)
    assert parse_hotkey("Escape") == (0, 0x1B)


def test_normalize():
    assert normalize_hotkey("alt+CONTROL+g") == "Ctrl+Alt+G"
    assert normalize_hotkey("Ctrl+Alt+;") == "Ctrl+Alt+;"


@pytest.mark.parametrize("bad", ["", "Ctrl+Alt", "Ctrl+Banana", "G+Ctrl"])
def test_parse_errors(bad):
    with pytest.raises(HotkeyParseError):
        parse_hotkey(bad)


def test_validation():
    assert validate_global_hotkey("Ctrl+Alt+G") is None
    assert validate_global_hotkey("G") is not None          # would break typing
    assert validate_global_hotkey("Shift+G") is not None
    assert validate_global_hotkey("Ctrl+C") is not None     # standard editing shortcut
    assert validate_global_hotkey("Escape", allow_bare=True) is None
    assert validate_global_hotkey("F13") is None
