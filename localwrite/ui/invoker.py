"""Thread helpers: run work in the background and hop back to the Qt UI thread."""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, Slot

log = logging.getLogger(__name__)


class UiInvoker(QObject):
    """Create on the UI thread; ``call(fn)`` from any thread runs fn on the UI thread."""

    _queued = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._queued.connect(self._run)

    @Slot(object)
    def _run(self, fn: Callable[[], Any]) -> None:
        try:
            fn()
        except Exception:  # noqa: BLE001
            log.exception("UI callback failed")

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        self._queued.emit(lambda: fn(*args, **kwargs))


def run_background(
    invoker: UiInvoker,
    work: Callable[[], Any],
    on_success: Callable[[Any], None] | None = None,
    on_error: Callable[[BaseException], None] | None = None,
    name: str = "LocalWriteWorker",
) -> threading.Thread:
    """Run ``work`` on a daemon thread and deliver the outcome on the UI thread."""

    def runner() -> None:
        try:
            result = work()
        except BaseException as exc:  # noqa: BLE001
            if on_error:
                invoker.call(on_error, exc)
            else:
                log.exception("Background task %s failed", name)
            return
        if on_success:
            invoker.call(on_success, result)

    t = threading.Thread(target=runner, name=name, daemon=True)
    t.start()
    return t
