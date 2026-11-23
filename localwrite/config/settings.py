"""Application settings: a typed dataclass persisted as JSON with validation."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from localwrite.core.modes import LEGACY_MODES, MODES

log = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"
RECOMMENDED_MODEL = "qwen2.5:3b"

DEFAULT_HOTKEYS: dict[str, str] = {
    "general": "Ctrl+Alt+G",
    "spelling": "Ctrl+Alt+S",
    "professional": "Ctrl+Alt+P",
    "quick": "Ctrl+Alt+Q",
    "close_popup": "Escape",
}

HOTKEY_LABELS: dict[str, str] = {
    "general": "General correction",
    "spelling": "Spelling correction",
    "professional": "Professional writing",
    "quick": "Quick fix",
    "close_popup": "Close the popup",
}

# Which writing mode each correction shortcut runs (None = the user's default mode).
HOTKEY_MODES: dict[str, str | None] = {
    "general": None,
    "spelling": "spelling",
    "professional": "professional",
    "quick": "quick",
}

POPUP_POSITIONS = ("smart", "cursor", "center", "top_right", "bottom_right")
POPUP_POSITION_LABELS = {
    "smart": "Near the text cursor (falls back to the mouse)",
    "cursor": "Near the mouse cursor",
    "center": "Center of the screen",
    "top_right": "Top-right corner",
    "bottom_right": "Bottom-right corner",
}

DEFAULT_EXCLUDED_APPS = [
    "keepass.exe", "keepassxc.exe", "1password.exe", "bitwarden.exe", "dashlane.exe",
    "lastpass.exe", "enpass.exe", "nordpass.exe", "credentialuibroker.exe", "consent.exe",
    "logonui.exe", "mstsc.exe",
]

_BOOL_FIELDS = (
    "assistant_enabled", "start_with_windows", "start_minimized", "minimize_to_tray",
    "close_to_tray", "show_notifications", "close_popup_after_replace",
    "restore_clipboard", "verify_before_replace", "realtime_enabled", "first_run_complete",
)


@dataclass
class Settings:
    # Ollama
    ollama_url: str = DEFAULT_OLLAMA_URL
    model: str = ""
    temperature: float = 0.2
    timeout_seconds: int = 90
    keep_alive: str = "15m"
    context_length: int = 4096
    # Writing
    default_mode: str = "grammar"
    custom_instruction: str = ""
    # Shortcuts
    hotkeys: dict = field(default_factory=lambda: dict(DEFAULT_HOTKEYS))
    # Popup
    popup_position: str = "smart"
    # Behaviour (assistant_enabled = global shortcuts on/off)
    assistant_enabled: bool = True
    start_with_windows: bool = False
    start_minimized: bool = False
    minimize_to_tray: bool = True
    close_to_tray: bool = True
    show_notifications: bool = True
    close_popup_after_replace: bool = True
    # Clipboard. There is deliberately no correction history: text is never stored.
    restore_clipboard: bool = True
    clipboard_restore_delay_ms: int = 600
    copy_timeout_ms: int = 900
    verify_before_replace: bool = True
    # Real-time assistance (advanced, off by default)
    realtime_enabled: bool = False
    realtime_excluded_apps: list = field(default_factory=lambda: list(DEFAULT_EXCLUDED_APPS))
    # Internal
    first_run_complete: bool = False

    def validated(self) -> "Settings":
        """Return a copy with every field coerced into its legal range."""
        s = Settings(**asdict(self))
        s.ollama_url = (str(s.ollama_url or "").strip() or DEFAULT_OLLAMA_URL).rstrip("/")
        if "://" not in s.ollama_url:
            s.ollama_url = "http://" + s.ollama_url
        s.model = str(s.model or "").strip()
        s.temperature = _clamp_float(s.temperature, 0.0, 1.5, 0.2)
        s.timeout_seconds = _clamp_int(s.timeout_seconds, 10, 600, 90)
        s.context_length = _clamp_int(s.context_length, 1024, 131072, 4096)
        s.keep_alive = str(s.keep_alive or "15m").strip() or "15m"
        s.default_mode = LEGACY_MODES.get(s.default_mode, s.default_mode)
        if s.default_mode not in MODES:
            s.default_mode = "grammar"
        s.custom_instruction = str(s.custom_instruction or "")[:2000]
        hk = dict(DEFAULT_HOTKEYS)
        if isinstance(s.hotkeys, dict):
            for key, value in s.hotkeys.items():
                if key in DEFAULT_HOTKEYS and isinstance(value, str):
                    hk[key] = value.strip()
        s.hotkeys = hk
        if s.popup_position not in POPUP_POSITIONS:
            s.popup_position = "smart"
        for name in _BOOL_FIELDS:
            setattr(s, name, bool(getattr(s, name)))
        s.clipboard_restore_delay_ms = _clamp_int(s.clipboard_restore_delay_ms, 100, 5000, 600)
        s.copy_timeout_ms = _clamp_int(s.copy_timeout_ms, 200, 5000, 900)
        if isinstance(s.realtime_excluded_apps, (list, tuple)):
            s.realtime_excluded_apps = sorted(
                {str(a).strip().lower() for a in s.realtime_excluded_apps if str(a).strip()}
            )
        else:
            s.realtime_excluded_apps = list(DEFAULT_EXCLUDED_APPS)
        return s

    def is_local_server(self) -> bool:
        from urllib.parse import urlparse

        host = (urlparse(self.ollama_url).hostname or "").lower()
        return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}

    def copy(self, **changes: Any) -> "Settings":
        data = asdict(self)
        data.update(changes)
        return Settings(**data).validated()


def _clamp_float(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, v))


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, v))


class SettingsStore:
    """Loads and atomically saves Settings to a JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings().validated()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("settings root is not an object")
        except (OSError, ValueError) as exc:
            log.warning("Settings file unreadable (%s); using defaults", type(exc).__name__)
            try:
                self.path.replace(self.path.with_suffix(".json.bak"))
            except OSError:
                pass
            return Settings().validated()
        known = {f.name for f in fields(Settings)}
        data = {k: v for k, v in raw.items() if k in known}
        try:
            settings = Settings(**data).validated()
        except TypeError:
            settings = Settings().validated()
        if set(raw) - known:
            # Drop keys from older versions (e.g. theme, history_enabled) right away.
            try:
                self.save(settings)
            except OSError:
                pass
        return settings

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(asdict(settings.validated()), indent=2, sort_keys=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".settings-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
