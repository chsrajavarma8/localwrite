"""Logging configuration.

Privacy rule: the application never logs user text. Log calls elsewhere only
record lengths, mode names, timings and error types.
"""
from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from localwrite import paths

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if getattr(root, "_localwrite_configured", False):
        return
    root.setLevel(level)
    handler = RotatingFileHandler(
        paths.log_dir() / "localwrite.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
    if sys.stderr is not None:  # pythonw has no console
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter(_FORMAT))
        console.setLevel(logging.WARNING)
        root.addHandler(console)
    root._localwrite_configured = True  # type: ignore[attr-defined]

    def _excepthook(exc_type, exc, tb):
        logging.getLogger("localwrite.crash").error("Unhandled exception", exc_info=(exc_type, exc, tb))

    def _thread_hook(args):
        logging.getLogger("localwrite.crash").error(
            "Unhandled exception in thread %s", args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = _excepthook
    threading.excepthook = _thread_hook
