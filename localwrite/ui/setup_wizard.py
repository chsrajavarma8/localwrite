"""First-run setup wizard: dependencies, Ollama, model choice and a test correction.

Nothing is installed or downloaded unless the user explicitly clicks a button
and confirms.
"""
from __future__ import annotations

import importlib
import sys
import webbrowser
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton,
    QVBoxLayout, QWizard, QWizardPage,
)

from localwrite.config.settings import RECOMMENDED_MODEL
from localwrite.core.cancel import CancelToken
from localwrite.core.correction_engine import CorrectionEngine
from localwrite.core.ollama_client import (
    OLLAMA_DOWNLOAD_URL, OllamaClient, OllamaError, find_ollama_executable, iter_recommended_models, start_ollama,
)
from localwrite.ui import theme
from localwrite.ui.icons import app_icon
from localwrite.ui.invoker import run_background
from localwrite.ui.widgets import Spinner, muted_label, set_variant

if TYPE_CHECKING:
    from localwrite.app_controller import AppController

TEST_SENTENCE = "i has went to the store yesterday and buyed three apple"


def _ok(text: str) -> str:
    return f'<span style="color:{theme.current().success}">✔</span> {text}'


def _bad(text: str) -> str:
    return f'<span style="color:{theme.current().danger}">✖</span> {text}'


class WelcomePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Welcome to LocalWrite")
        self.setSubTitle("Your private AI writing assistant for every app on Windows.")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "<p>LocalWrite fixes spelling and grammar and rewrites text anywhere: browsers, WhatsApp, Telegram, "
            "Discord, Word, Notepad, VS Code, Gmail and more.</p>"
            "<p><b>How it works:</b> select text, press <b>Ctrl+Alt+G</b>, review the suggestion, click "
            "<b>Accept &amp; Replace</b>.</p>"
            "<p><b>Privacy first:</b> the AI runs locally through <b>Ollama</b>. Your text never leaves this "
            "computer, LocalWrite never records keystrokes, and it only reads the text you select when you ask.</p>"
            "<p>This wizard checks your setup and helps you pick a model. It will never install or download "
            "anything without asking you first.</p>"
        ))
        for l in self.findChildren(QLabel):
            l.setWordWrap(True)
        lay.addStretch(1)


class EnvironmentPage(QWizardPage):
    def __init__(self, wizard: "SetupWizard") -> None:
        super().__init__()
        self.wiz = wizard
        self.setTitle("Check your system")
        self.setSubTitle("LocalWrite needs a few Python libraries and a running Ollama server.")
        lay = QVBoxLayout(self)
        self.checks = QLabel()
        self.checks.setTextFormat(Qt.TextFormat.RichText)
        self.checks.setWordWrap(True)
        lay.addWidget(self.checks)
        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("Ollama server:"))
        self.url = QLineEdit(wizard.c.settings.ollama_url)
        url_row.addWidget(self.url, 1)
        lay.addLayout(url_row)
        btns = QHBoxLayout()
        self.recheck = QPushButton("Check again")
        self.recheck.clicked.connect(self.run_checks)
        self.start_btn = QPushButton("Start Ollama")
        self.start_btn.clicked.connect(self._start_ollama)
        self.download_btn = QPushButton("Open Ollama download page")
        self.download_btn.clicked.connect(lambda: webbrowser.open(OLLAMA_DOWNLOAD_URL))
        self.spinner = Spinner(16)
        self.spinner.hide()
        for b in (self.recheck, self.start_btn, self.download_btn):
            btns.addWidget(b)
        btns.addWidget(self.spinner)
        btns.addStretch(1)
        lay.addLayout(btns)
        self.help = muted_label()
        self.help.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.help)
        lay.addStretch(1)
        self._server_ok = False

    def initializePage(self) -> None:  # noqa: N802
        self.run_checks()

    def isComplete(self) -> bool:  # noqa: N802
        return self._server_ok

    def run_checks(self) -> None:
        lines = []
        py_ok = sys.version_info >= (3, 11)
        lines.append((_ok if py_ok else _bad)(f"Python {sys.version.split()[0]}" + ("" if py_ok else " (3.11+ required)")))
        for mod, label in (("PySide6", "PySide6 (user interface)"), ("requests", "requests (Ollama API)"),
                           ("json", "Python standard library")):
            try:
                importlib.import_module(mod)
                lines.append(_ok(label))
            except ImportError:
                lines.append(_bad(f"{label} missing - run install.bat"))
        lines.append((_ok if sys.platform == "win32" else _bad)("Windows"))
        exe = find_ollama_executable()
        self._exe = exe
        lines.append(_ok(f"Ollama installed ({exe})") if exe else
                     _bad("Ollama was not found on this computer"))
        self._base_lines = lines
        self.checks.setText("<br>".join(lines + ["… Checking the Ollama server"]))
        self.spinner.start()
        self.recheck.setEnabled(False)
        self._server_ok = False
        self.completeChanged.emit()
        url = self.url.text()
        run_background(self.wiz.c.invoker, lambda: OllamaClient(url).version(), self._server_done,
                       self._server_failed)

    def _server_done(self, version: str) -> None:
        self.spinner.stop()
        self.recheck.setEnabled(True)
        self._server_ok = True
        self.wiz.url = self.url.text()
        self.checks.setText("<br>".join(self._base_lines + [_ok(f"Ollama server is running (version {version})")]))
        self.start_btn.hide()
        self.download_btn.hide()
        self.help.setText("All good. Click Next to choose a model.")
        self.completeChanged.emit()

    def _server_failed(self, exc: BaseException) -> None:
        self.spinner.stop()
        self.recheck.setEnabled(True)
        self.checks.setText("<br>".join(self._base_lines + [_bad(f"No Ollama server at {self.url.text()}")]))
        self.start_btn.setVisible(self._exe is not None)
        self.download_btn.setVisible(self._exe is None)
        if self._exe is None:
            self.help.setText(
                "Install Ollama (free) to run AI models locally:\n"
                f"  1. Open {OLLAMA_DOWNLOAD_URL} (button above)\n"
                "  2. Download and run OllamaSetup.exe\n"
                "  3. Ollama starts automatically - then click 'Check again'."
            )
        else:
            self.help.setText("Ollama is installed but not running. Click 'Start Ollama' (or launch it from the "
                              "Start menu), wait a few seconds, then click 'Check again'.")
        self.completeChanged.emit()

    def _start_ollama(self) -> None:
        if self._exe is None:
            return
        try:
            start_ollama(self._exe)
        except OSError as exc:
            self.help.setText(f"Couldn't start Ollama: {exc}")
            return
        self.help.setText("Starting Ollama...")
        from PySide6.QtCore import QTimer

        QTimer.singleShot(3500, self.run_checks)


class ModelPage(QWizardPage):
    def __init__(self, wizard: "SetupWizard") -> None:
        super().__init__()
        self.wiz = wizard
        self.setTitle("Choose a model")
        self.setSubTitle("Pick one of the models installed in Ollama. Smaller models are faster.")
        lay = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.setMinimumHeight(150)
        self.list.currentItemChanged.connect(lambda *_: self.completeChanged.emit())
        lay.addWidget(self.list)
        self.note = muted_label()
        lay.addWidget(self.note)
        rec = "<br>".join(f"<b>{n}</b> — {d}" for n, d in iter_recommended_models())
        lay.addWidget(QLabel(f"<span>Suggestions:</span><br>{rec}"))
        dl = QHBoxLayout()
        self.pull_name = QLineEdit(RECOMMENDED_MODEL)
        self.pull_btn = QPushButton("Download model...")
        self.pull_btn.clicked.connect(self._pull)
        self.cancel_pull = set_variant(QPushButton("Cancel download"), "ghost")
        self.cancel_pull.hide()
        dl.addWidget(QLabel("Download:"))
        dl.addWidget(self.pull_name, 1)
        dl.addWidget(self.pull_btn)
        dl.addWidget(self.cancel_pull)
        lay.addLayout(dl)
        self.progress = QProgressBar()
        self.progress.hide()
        self.progress_label = muted_label()
        lay.addWidget(self.progress)
        lay.addWidget(self.progress_label)
        lay.addStretch(1)
        self._pull_cancel: CancelToken | None = None
        self.cancel_pull.clicked.connect(lambda: self._pull_cancel and self._pull_cancel.cancel())

    def initializePage(self) -> None:  # noqa: N802
        self.load_models()

    def isComplete(self) -> bool:  # noqa: N802
        item = self.list.currentItem()
        return bool(item and item.data(Qt.ItemDataRole.UserRole)) and self._pull_cancel is None

    def selected(self) -> str:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def load_models(self, select: str | None = None) -> None:
        self.note.setText("Loading installed models...")

        def done(models) -> None:
            self.list.clear()
            usable = [m for m in models if not m.is_embedding_model]
            prefer = select or self.wiz.c.settings.model
            row = 0
            for i, m in enumerate(usable):
                details = " · ".join(b for b in (m.parameter_size, m.size_label) if b)
                rec = "  (recommended)" if m.name == RECOMMENDED_MODEL else ""
                item = QListWidgetItem(f"{m.name}{rec}\n{details}")
                item.setData(Qt.ItemDataRole.UserRole, m.name)
                self.list.addItem(item)
                if m.name == prefer or (not prefer and m.name == RECOMMENDED_MODEL):
                    row = i
            if usable:
                self.list.setCurrentRow(row)
                self.note.setText(f"{len(usable)} model(s) installed.")
            else:
                self.note.setText(f"No models are installed yet. Download one below - {RECOMMENDED_MODEL} "
                                  "is recommended (about 1.9 GB).")
            self.completeChanged.emit()

        def failed(exc) -> None:
            self.note.setText(f"Couldn't list models: {getattr(exc, 'title', exc)}")

        url = self.wiz.url
        run_background(self.wiz.c.invoker, lambda: OllamaClient(url).list_models(), done, failed)

    def _pull(self) -> None:
        name = self.pull_name.text().strip()
        if not name:
            return
        answer = QMessageBox.question(
            self, "Download model",
            f"Download '{name}' from the Ollama library?\n\nThis can be several gigabytes and may take a while. "
            "The model is stored by Ollama on this computer.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._pull_cancel = CancelToken()
        self.completeChanged.emit()
        self.pull_btn.setEnabled(False)
        self.cancel_pull.show()
        self.progress.show()
        self.progress.setRange(0, 0)
        token = self._pull_cancel
        invoker = self.wiz.c.invoker

        def progress(status: str, done: int, total: int) -> None:
            def ui() -> None:
                if total:
                    self.progress.setRange(0, 1000)
                    self.progress.setValue(int(done * 1000 / total))
                    self.progress_label.setText(f"{status} · {done / 1e9:.2f} / {total / 1e9:.2f} GB")
                else:
                    self.progress.setRange(0, 0)
                    self.progress_label.setText(status)
            invoker.call(ui)

        def finished(_r) -> None:
            self._end_pull()
            self.progress_label.setText(f"✔ {name} downloaded.")
            self.load_models(select=name)

        def failed(exc) -> None:
            self._end_pull()
            self.progress_label.setText(f"✖ {getattr(exc, 'title', exc)} {getattr(exc, 'detail', '')}")

        url = self.wiz.url
        run_background(invoker, lambda: OllamaClient(url).pull_model(name, progress, token), finished, failed)

    def _end_pull(self) -> None:
        self._pull_cancel = None
        self.pull_btn.setEnabled(True)
        self.cancel_pull.hide()
        self.progress.hide()
        self.completeChanged.emit()


class TestPage(QWizardPage):
    def __init__(self, wizard: "SetupWizard") -> None:
        super().__init__()
        self.wiz = wizard
        self.setTitle("Test a correction")
        self.setSubTitle("Let's make sure the model works.")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Test sentence:  <i>{TEST_SENTENCE}</i>"))
        row = QHBoxLayout()
        self.run_btn = set_variant(QPushButton("Run test"), "primary")
        self.run_btn.clicked.connect(self.run_test)
        self.spinner = Spinner(16)
        self.spinner.hide()
        row.addWidget(self.run_btn)
        row.addWidget(self.spinner)
        row.addStretch(1)
        lay.addLayout(row)
        self.result = QLabel()
        self.result.setWordWrap(True)
        self.result.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.result)
        self.hint = muted_label("The first request can take longer while Ollama loads the model into memory.")
        lay.addWidget(self.hint)
        lay.addStretch(1)
        self._passed = False

    def initializePage(self) -> None:  # noqa: N802
        self._passed = False
        self.result.setText("")
        self.run_test()

    def isComplete(self) -> bool:  # noqa: N802
        return self._passed

    def run_test(self) -> None:
        model = self.wiz.model_page.selected()
        self.run_btn.setEnabled(False)
        self.spinner.start()
        self.result.setText(f"Asking <b>{model}</b>...")
        s = self.wiz.c.settings
        url = self.wiz.url

        def work():
            engine = CorrectionEngine(OllamaClient(url), model, temperature=s.temperature,
                                      timeout=max(120, s.timeout_seconds), keep_alive=s.keep_alive,
                                      context_length=s.context_length)
            return engine.correct(TEST_SENTENCE, "grammar")

        def done(res) -> None:
            self.spinner.stop()
            self.run_btn.setEnabled(True)
            self._passed = bool(res.corrected.strip())
            self.result.setText(_ok(f"Works! ({res.elapsed:.1f}s)") + f"<br><br><b>{res.corrected}</b>")
            self.completeChanged.emit()

        def failed(exc) -> None:
            self.spinner.stop()
            self.run_btn.setEnabled(True)
            title = exc.title if isinstance(exc, OllamaError) else str(exc)
            hint = exc.hint if isinstance(exc, OllamaError) else ""
            self.result.setText(_bad(title) + (f"<br>{hint}" if hint else ""))
            self.completeChanged.emit()

        run_background(self.wiz.c.invoker, work, done, failed)


class FinishPage(QWizardPage):
    def __init__(self, wizard: "SetupWizard") -> None:
        super().__init__()
        self.wiz = wizard
        self.setTitle("You're all set")
        lay = QVBoxLayout(self)
        hk = wizard.c.settings.hotkeys
        lay.addWidget(QLabel(
            "<p>Select text in any app and press:</p>"
            f"<p><b>{hk.get('general')}</b> — correct grammar &amp; spelling<br>"
            f"<b>{hk.get('spelling')}</b> — spelling only<br>"
            f"<b>{hk.get('professional')}</b> — professional rewrite<br>"
            f"<b>{hk.get('quick')}</b> — quick fix (obvious typos only)<br>"
            "<b>Esc</b> — close the popup</p>"
            "<p>LocalWrite lives in the system tray (bottom-right, near the clock).</p>"
        ))
        self.autostart = QCheckBox("Start LocalWrite automatically when I sign in to Windows")
        self.autostart.setChecked(wizard.c.settings.start_with_windows)
        lay.addWidget(self.autostart)
        lay.addStretch(1)


class SetupWizard(QWizard):
    def __init__(self, controller: "AppController") -> None:
        super().__init__()
        self.c = controller
        self.url = controller.settings.ollama_url
        self.setWindowTitle("LocalWrite setup")
        self.setWindowIcon(app_icon())
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.resize(720, 560)
        self.addPage(WelcomePage())
        self.env_page = EnvironmentPage(self)
        self.addPage(self.env_page)
        self.model_page = ModelPage(self)
        self.addPage(self.model_page)
        self.addPage(TestPage(self))
        self.finish_page = FinishPage(self)
        self.addPage(self.finish_page)
        self.finished.connect(self._finished)

    def _finished(self, result: int) -> None:
        if result == QWizard.DialogCode.Accepted:
            self.c.apply_settings(self.c.settings.copy(
                ollama_url=self.url,
                model=self.model_page.selected() or self.c.settings.model,
                start_with_windows=self.finish_page.autostart.isChecked(),
                first_run_complete=True,
            ))
            self.c.refresh_ollama()
            self.c.notify("LocalWrite is ready", f"Select text anywhere and press {self.c.settings.hotkeys.get('general')}.")
        else:
            if not self.c.settings.first_run_complete:
                self.c.apply_settings(self.c.settings.copy(first_run_complete=True))
                self.c.notify("Setup skipped", "You can run the setup wizard any time from Settings.")
