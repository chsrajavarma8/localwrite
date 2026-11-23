"""OllamaClient against a fake local HTTP server that mimics the Ollama API."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from localwrite.core.cancel import CancelToken
from localwrite.core.ollama_client import (
    OllamaCancelledError, OllamaClient, OllamaConnectionError, OllamaModelNotFoundError, OllamaTimeoutError,
)

CRLF = b"\r\n"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # real Ollama streams with chunked transfer encoding

    def _chunk(self, data: bytes):
        self.wfile.write(("%X" % len(data)).encode() + CRLF + data + CRLF)
        self.wfile.flush()

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/version":
            self._json(200, {"version": "0.99.0"})
        elif self.path == "/api/tags":
            self._json(200, {"models": [
                {"name": "qwen2.5:3b", "size": 1_900_000_000, "details": {"parameter_size": "3.1B", "family": "qwen2"}},
                {"name": "llama3.2:3b", "size": 2_000_000_000, "details": {}},
            ]})
        else:
            self._json(404, {"error": "nope"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        if payload.get("model") == "missing":
            self._json(404, {"error": "model 'missing' not found"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            for wd in ["I ", "have ", "an ", "apple."]:
                if payload.get("model") == "slow":
                    time.sleep(0.5)
                line = json.dumps({"message": {"role": "assistant", "content": wd}, "done": False}) + "\n"
                self._chunk(line.encode())
            self._chunk((json.dumps({"message": {"content": ""}, "done": True}) + "\n").encode())
            self._chunk(b"")
        except OSError:
            pass  # client hung up (cancel / timeout)


class QuietServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        pass  # the cancel/timeout tests hang up on purpose


@pytest.fixture(scope="module")
def server():
    srv = QuietServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_version_and_models(server):
    c = OllamaClient(server)
    assert c.is_running()
    assert c.version() == "0.99.0"
    models = c.list_models()
    assert [m.name for m in models] == ["llama3.2:3b", "qwen2.5:3b"]
    assert models[1].size_label == "1.9 GB"


def test_chat_streams(server):
    tokens = []
    out = OllamaClient(server).chat("qwen2.5:3b", [{"role": "user", "content": "x"}], on_token=tokens.append)
    assert out == "I have an apple."
    assert tokens == ["I ", "have ", "an ", "apple."]


def test_missing_model(server):
    with pytest.raises(OllamaModelNotFoundError) as ei:
        OllamaClient(server).chat("missing", [])
    assert "ollama pull missing" in ei.value.hint


def test_cancel(server):
    token = CancelToken()
    threading.Timer(0.3, token.cancel).start()
    start = time.monotonic()
    with pytest.raises(OllamaCancelledError):
        OllamaClient(server).chat("slow", [], cancel=token)
    assert time.monotonic() - start < 1.5


def test_timeout(server):
    with pytest.raises(OllamaTimeoutError):
        OllamaClient(server).chat("slow", [], timeout=0.8)


def test_localhost_is_requested_via_ipv4():
    c = OllamaClient("http://localhost:11434")
    assert c.base_url == "http://localhost:11434"
    assert c._url("/api/tags") == "http://127.0.0.1:11434/api/tags"


@pytest.mark.ollama
def test_selected_model_reaches_real_ollama():
    """The model chosen in the UI is the one sent to Ollama."""
    import os

    from localwrite.core.correction_engine import CorrectionEngine

    client = OllamaClient("http://localhost:11434")
    model = os.environ.get("LOCALWRITE_TEST_MODEL", "llama3.2:3b")
    engine = CorrectionEngine(client, model, timeout=180)
    assert engine.correct("i has a apple", "grammar").corrected.strip()
    engine.model = "localwrite-missing-model:1b"
    with pytest.raises(OllamaModelNotFoundError):
        engine.correct("i has a apple", "grammar")


def test_connection_refused():
    c = OllamaClient("http://127.0.0.1:9", connect_timeout=0.5)
    assert not c.is_running()
    with pytest.raises(OllamaConnectionError):
        c.chat("x", [])
