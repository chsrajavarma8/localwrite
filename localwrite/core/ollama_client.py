"""Minimal, dependable client for the local Ollama HTTP API.

Design notes
- ``trust_env`` is disabled so HTTP(S)_PROXY variables can never route user text
  through a proxy server: requests go straight to the configured Ollama URL.
- Chat responses are streamed so the UI can show progress and so a request can be
  cancelled mid-generation by closing the response (which also stops Ollama).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import requests

from localwrite.core.cancel import CancelToken

log = logging.getLogger(__name__)

OLLAMA_DOWNLOAD_URL = "https://ollama.com/download/windows"

TROUBLESHOOTING = (
    "1. Make sure Ollama is installed (official installer: https://ollama.com/download/windows).\n"
    "2. Start Ollama from the Start menu (a llama icon appears in the system tray), or run "
    "'ollama serve' in a terminal.\n"
    "3. Check the server address in Settings (default http://localhost:11434).\n"
    "4. Make sure at least one model is installed, e.g. run 'ollama pull qwen2.5:3b'.\n"
    "5. If a firewall or antivirus blocks local connections, allow ollama.exe."
)


class OllamaError(Exception):
    """Base error with a short title, detail and an actionable hint for the UI."""

    def __init__(self, title: str, detail: str = "", hint: str = "") -> None:
        super().__init__(title if not detail else f"{title}: {detail}")
        self.title = title
        self.detail = detail
        self.hint = hint


class OllamaConnectionError(OllamaError):
    pass


class OllamaTimeoutError(OllamaError):
    pass


class OllamaModelNotFoundError(OllamaError):
    pass


class OllamaCancelledError(OllamaError):
    pass


class EmptyResponseError(OllamaError):
    pass


@dataclass(frozen=True)
class ModelInfo:
    name: str
    size_bytes: int = 0
    parameter_size: str = ""
    family: str = ""
    quantization: str = ""

    @property
    def size_label(self) -> str:
        if not self.size_bytes:
            return ""
        gb = self.size_bytes / 1_000_000_000
        return f"{gb:.1f} GB" if gb >= 1 else f"{self.size_bytes / 1_000_000:.0f} MB"

    @property
    def is_embedding_model(self) -> bool:
        n = self.name.lower()
        return "embed" in n or self.family.lower() in {"bert", "nomic-bert"}


def normalize_url(url: str) -> str:
    url = (url or "").strip() or "http://localhost:11434"
    if "://" not in url:
        url = "http://" + url
    return url.rstrip("/")


def _request_url(url: str) -> str:
    """Use 127.0.0.1 for 'localhost'.

    Windows resolves localhost to ::1 first and a refused IPv6 connection takes
    about two seconds to fail before IPv4 is tried; Ollama listens on IPv4.
    """
    return re.sub(r"^(https?://)localhost(?=[:/]|$)", r"\g<1>127.0.0.1", url, flags=re.I)


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", connect_timeout: float = 3.0) -> None:
        self.base_url = normalize_url(base_url)
        self._request_base = _request_url(self.base_url)
        self.connect_timeout = connect_timeout

    # ------------------------------------------------------------------ helpers
    def _session(self) -> requests.Session:
        s = requests.Session()
        s.trust_env = False  # never use system proxies for local inference
        return s

    def _url(self, path: str) -> str:
        return f"{self._request_base}{path}"

    def _connection_error(self, exc: Exception) -> OllamaConnectionError:
        return OllamaConnectionError(
            "Can't reach Ollama",
            f"No Ollama server is answering at {self.base_url}.",
            TROUBLESHOOTING,
        )

    def _get_json(self, path: str, timeout: float = 5.0) -> dict:
        try:
            with self._session() as s:
                r = s.get(self._url(path), timeout=(self.connect_timeout, timeout))
        except requests.exceptions.ConnectTimeout as exc:
            raise self._connection_error(exc) from exc
        except requests.exceptions.Timeout as exc:
            raise OllamaTimeoutError("Ollama did not respond in time", str(type(exc).__name__)) from exc
        except requests.exceptions.RequestException as exc:
            raise self._connection_error(exc) from exc
        if r.status_code != 200:
            raise OllamaError("Unexpected response from Ollama", f"HTTP {r.status_code} for {path}")
        try:
            return r.json()
        except ValueError as exc:
            raise OllamaError("Invalid response from Ollama", "The server did not return JSON.") from exc

    # ------------------------------------------------------------------ status
    def version(self) -> str:
        return str(self._get_json("/api/version", timeout=4).get("version", ""))

    def is_running(self) -> bool:
        try:
            self.version()
            return True
        except OllamaError:
            return False

    def list_models(self) -> list[ModelInfo]:
        data = self._get_json("/api/tags", timeout=8)
        models = []
        for m in data.get("models", []) or []:
            details = m.get("details") or {}
            models.append(
                ModelInfo(
                    name=m.get("name") or m.get("model") or "",
                    size_bytes=int(m.get("size") or 0),
                    parameter_size=str(details.get("parameter_size") or ""),
                    family=str(details.get("family") or ""),
                    quantization=str(details.get("quantization_level") or ""),
                )
            )
        models = [m for m in models if m.name]
        models.sort(key=lambda m: m.name.lower())
        return models

    # ------------------------------------------------------------------ chat
    def chat(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        timeout: float = 90.0,
        keep_alive: str = "15m",
        num_ctx: int | None = None,
        num_predict: int | None = None,
        on_token: Callable[[str], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> str:
        """Stream a chat completion and return the full assistant message content."""
        if not model:
            raise OllamaModelNotFoundError(
                "No model selected", "Choose a model in Settings or run the setup wizard.",
                "Installed models are listed in Settings > AI model.",
            )
        cancel = cancel or CancelToken()
        options: dict = {"temperature": float(temperature)}
        if num_ctx:
            options["num_ctx"] = int(num_ctx)
        if num_predict:
            options["num_predict"] = int(num_predict)
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": keep_alive,
            "options": options,
        }

        session = self._session()
        state: dict = {"resp": None}

        def abort() -> None:
            resp = state.get("resp")
            try:
                if resp is not None:
                    resp.close()
                session.close()
            except Exception:  # noqa: BLE001
                pass

        timer = threading.Timer(timeout, lambda: cancel.cancel("timeout"))
        timer.daemon = True
        remove_cb = cancel.add_callback(abort)
        timer.start()
        started = time.monotonic()
        parts: list[str] = []
        try:
            try:
                resp = session.post(
                    self._url("/api/chat"), json=payload, stream=True,
                    timeout=(self.connect_timeout, timeout),
                )
            except requests.exceptions.ConnectTimeout as exc:
                self._raise_if_cancelled(cancel, timeout)
                raise self._connection_error(exc) from exc
            except requests.exceptions.Timeout as exc:
                raise self._timeout_error(timeout) from exc
            except requests.exceptions.RequestException as exc:
                self._raise_if_cancelled(cancel, timeout)
                raise self._connection_error(exc) from exc
            state["resp"] = resp
            if cancel.cancelled:
                abort()
            self._check_status(resp, model)
            try:
                for line in resp.iter_lines(chunk_size=256):
                    if cancel.cancelled:
                        break
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if obj.get("error"):
                        raise OllamaError("The model reported an error", str(obj["error"]))
                    piece = (obj.get("message") or {}).get("content") or ""
                    if piece:
                        parts.append(piece)
                        if on_token:
                            on_token(piece)
                    if obj.get("done"):
                        break
            except requests.exceptions.Timeout as exc:
                raise self._timeout_error(timeout) from exc
            except (requests.exceptions.RequestException, AttributeError, ValueError, OSError) as exc:
                # Closing the response from another thread surfaces as one of these.
                self._raise_if_cancelled(cancel, timeout)
                raise OllamaConnectionError(
                    "Connection to Ollama was interrupted", type(exc).__name__, TROUBLESHOOTING
                ) from exc
            self._raise_if_cancelled(cancel, timeout)
        finally:
            timer.cancel()
            remove_cb()
            abort()
        log.debug("Chat completed in %.2fs", time.monotonic() - started)
        return "".join(parts)

    def _timeout_error(self, timeout: float) -> OllamaTimeoutError:
        return OllamaTimeoutError(
            "The model took too long to respond",
            f"No complete answer within {int(timeout)} seconds.",
            "Large models can be slow on modest hardware. Try a smaller model such as qwen2.5:3b, "
            "shorter text, or increase 'Maximum response time' in Settings.",
        )

    def _raise_if_cancelled(self, cancel: CancelToken, timeout: float) -> None:
        if cancel.cancelled:
            if cancel.reason == "timeout":
                raise self._timeout_error(timeout)
            raise OllamaCancelledError("Cancelled")

    @staticmethod
    def _check_status(resp: requests.Response, model: str) -> None:
        if resp.status_code == 200:
            return
        try:
            message = str(resp.json().get("error", ""))
        except ValueError:
            message = resp.text[:300]
        if resp.status_code == 404 or "not found" in message.lower():
            raise OllamaModelNotFoundError(
                f"Model '{model}' is not installed",
                message,
                f"Install it with:  ollama pull {model}\nor choose another model in Settings.",
            )
        raise OllamaError(f"Ollama returned HTTP {resp.status_code}", message)

    # ------------------------------------------------------------------ pull
    def pull_model(
        self,
        name: str,
        on_progress: Callable[[str, int, int], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> None:
        """Download a model. Only ever called after explicit user confirmation."""
        cancel = cancel or CancelToken()
        session = self._session()
        remove_cb = cancel.add_callback(session.close)
        try:
            try:
                resp = session.post(
                    self._url("/api/pull"), json={"model": name, "stream": True},
                    stream=True, timeout=(self.connect_timeout, 600),
                )
            except requests.exceptions.RequestException as exc:
                if cancel.cancelled:
                    raise OllamaCancelledError("Download cancelled") from exc
                raise self._connection_error(exc) from exc
            if resp.status_code != 200:
                raise OllamaError("Download failed", f"HTTP {resp.status_code}: {resp.text[:200]}")
            try:
                for line in resp.iter_lines():
                    if cancel.cancelled:
                        raise OllamaCancelledError("Download cancelled")
                    if not line:
                        continue
                    obj = json.loads(line)
                    if obj.get("error"):
                        raise OllamaError("Download failed", str(obj["error"]))
                    if on_progress:
                        on_progress(str(obj.get("status", "")), int(obj.get("completed") or 0), int(obj.get("total") or 0))
                    if obj.get("status") == "success":
                        return
            except (requests.exceptions.RequestException, OSError, AttributeError) as exc:
                if cancel.cancelled:
                    raise OllamaCancelledError("Download cancelled") from exc
                raise OllamaConnectionError("Download interrupted", type(exc).__name__) from exc
        finally:
            remove_cb()
            session.close()


# ---------------------------------------------------------------------- install detection
def find_ollama_executable() -> Path | None:
    candidates: list[Path] = []
    which = shutil.which("ollama")
    if which:
        candidates.append(Path(which))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Programs" / "Ollama" / "ollama.exe")
    for env in ("ProgramFiles", "ProgramW6432"):
        base = os.environ.get(env)
        if base:
            candidates.append(Path(base) / "Ollama" / "ollama.exe")
    for c in candidates:
        if c.is_file():
            return c
    return None


def start_ollama(executable: Path) -> None:
    """Start the user's installed Ollama (only on explicit request).

    Prefers the tray app ("ollama app.exe") which manages the server itself;
    falls back to ``ollama serve`` in a hidden window.
    """
    app = executable.with_name("ollama app.exe")
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if app.is_file():
        subprocess.Popen([str(app)], creationflags=flags, close_fds=True)
    else:
        subprocess.Popen([str(executable), "serve"], creationflags=flags | no_window, close_fds=True)


def iter_recommended_models() -> Iterable[tuple[str, str]]:
    yield "qwen2.5:3b", "Recommended - fast, good quality, ~1.9 GB, runs on most PCs"
    yield "llama3.2:3b", "Lightweight alternative, ~2.0 GB"
    yield "qwen2.5:7b", "Better quality for PCs with 16 GB+ RAM or a GPU, ~4.7 GB"
    yield "gemma3:4b", "Good writing quality, ~3.3 GB"
