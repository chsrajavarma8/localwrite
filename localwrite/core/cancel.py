"""Thread-safe cancellation token shared between the UI and background workers."""
from __future__ import annotations

import threading
from typing import Callable


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[], None]] = []
        self.reason = ""

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self, reason: str = "cancelled") -> None:
        with self._lock:
            if self._event.is_set():
                return
            self.reason = reason
            self._event.set()
            callbacks = list(self._callbacks)
        for cb in callbacks:
            try:
                cb()
            except Exception:  # noqa: BLE001 - best effort abort
                pass

    def add_callback(self, cb: Callable[[], None]) -> Callable[[], None]:
        """Register cb to run on cancel (immediately if already cancelled). Returns a remover."""
        with self._lock:
            already = self._event.is_set()
            if not already:
                self._callbacks.append(cb)
        if already:
            cb()

        def remove() -> None:
            with self._lock:
                if cb in self._callbacks:
                    self._callbacks.remove(cb)

        return remove
