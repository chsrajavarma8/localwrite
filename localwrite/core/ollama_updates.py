"""Detect whether a newer Ollama release is available - without sending any user data.

Two sources:
1. Local (always, offline): the Ollama desktop app's own updater writes
   "New update available at .../vX.Y.Z/OllamaSetup.exe" to its log files in
   %LOCALAPPDATA%\\Ollama. Reading them needs no network access at all.
2. Online (optional, off by default): ask GitHub for the latest Ollama release.
   The request carries no user text, settings or usage data - only a generic
   User-Agent - and failures are ignored so LocalWrite keeps working offline.

LocalWrite never updates Ollama itself; it only shows a notice.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import requests

log = logging.getLogger(__name__)

RELEASES_API = "https://api.github.com/repos/ollama/ollama/releases/latest"
DOWNLOAD_PAGE = "https://ollama.com/download/windows"
_LOG_UPDATE_RE = re.compile(r"New update available at \S*?/v(\d+(?:\.\d+){1,3})/", re.I)
_MAX_LOG_BYTES = 2_000_000


@dataclass(frozen=True)
class UpdateInfo:
    installed: str
    latest: str
    source: str  # "local" | "online"


def parse_version(text: str) -> tuple[int, ...] | None:
    m = re.match(r"^\s*v?(\d+(?:\.\d+){0,3})", text or "")
    if not m:
        return None
    return tuple(int(p) for p in m.group(1).split("."))


def is_newer(candidate: str, installed: str) -> bool:
    a, b = parse_version(candidate), parse_version(installed)
    if a is None or b is None:
        return False
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def ollama_log_dir() -> Path | None:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return None
    path = Path(base) / "Ollama"
    return path if path.is_dir() else None


def latest_from_local_logs(log_dir: Path | None = None) -> str | None:
    """Newest version Ollama's own updater has announced in its local app logs."""
    log_dir = log_dir or ollama_log_dir()
    if log_dir is None:
        return None
    best: str | None = None
    for path in sorted(log_dir.glob("app*.log")):
        try:
            if path.stat().st_size > _MAX_LOG_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for version in _LOG_UPDATE_RE.findall(text):
            if best is None or is_newer(version, best):
                best = version
    return best


def latest_from_github(timeout: float = 5.0) -> str | None:
    """Latest release tag from GitHub. Sends no user data; returns None on any failure."""
    try:
        with requests.Session() as s:
            r = s.get(RELEASES_API, timeout=timeout,
                      headers={"Accept": "application/vnd.github+json", "User-Agent": "LocalWrite-update-check"})
        if r.status_code != 200:
            return None
        tag = str(r.json().get("tag_name") or "")
        return tag.lstrip("vV") if parse_version(tag) else None
    except (requests.RequestException, ValueError):
        return None


def check_for_update(installed: str, online: bool = False, log_dir: Path | None = None) -> UpdateInfo | None:
    """Return update info if a newer Ollama than ``installed`` is known, else None."""
    if not parse_version(installed):
        return None
    local = latest_from_local_logs(log_dir)
    if local and is_newer(local, installed):
        return UpdateInfo(installed, local, "local")
    if online:
        remote = latest_from_github()
        if remote and is_newer(remote, installed):
            return UpdateInfo(installed, remote, "online")
    return None
