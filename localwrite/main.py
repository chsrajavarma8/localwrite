"""Application entry point."""
from __future__ import annotations

import argparse
import ctypes
import getpass
import hashlib
import logging
import os
import sys

from localwrite import __app_name__, __version__, paths
from localwrite.core.logging_setup import setup_logging

log = logging.getLogger("localwrite")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="LocalWrite", description="Private local AI writing assistant")
    p.add_argument("--minimized", action="store_true", help="start in the system tray")
    p.add_argument("--setup", action="store_true", help="open the setup wizard")
    p.add_argument("--version", action="version", version=f"{__app_name__} {__version__}")
    return p.parse_known_args(argv)[0]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if sys.platform != "win32":
        print("LocalWrite runs on Windows only.", file=sys.stderr)
        return 1
    setup_logging()
    log.info("Starting %s %s (Python %s)", __app_name__, __version__, sys.version.split()[0])

    try:  # own taskbar identity (instead of python.exe's)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LocalWrite.Desktop")
    except (AttributeError, OSError):
        pass

    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication

    from localwrite.config.settings import SettingsStore
    from localwrite.ui.icons import app_icon

    app = QApplication(sys.argv[:1])
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())

    # Single instance: a second launch just asks the running one to show itself.
    server_name = f"LocalWrite-{getpass.getuser()}"
    if os.environ.get("LOCALWRITE_HOME"):  # isolated profile (tests, portable use): separate instance
        server_name += "-" + hashlib.sha1(str(paths.data_dir()).encode()).hexdigest()[:10]
    probe = QLocalSocket()
    probe.connectToServer(server_name)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(300)
        probe.disconnectFromServer()
        log.info("Another instance is running; asked it to show itself")
        return 0
    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    server.listen(server_name)

    from localwrite.app_controller import AppController

    controller = AppController(app, SettingsStore(paths.settings_file()),
                               start_minimized=args.minimized, force_setup=args.setup)

    def on_connection() -> None:
        sock = server.nextPendingConnection()
        if sock is not None:
            sock.readyRead.connect(lambda: (sock.readAll(), controller.show_main_window()))

    server.newConnection.connect(on_connection)
    controller.start()
    try:
        return app.exec()
    finally:
        controller.shutdown()
        server.close()


if __name__ == "__main__":
    sys.exit(main())
