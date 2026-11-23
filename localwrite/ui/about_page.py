"""About: what LocalWrite is, how to use it, the privacy promise and troubleshooting."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from localwrite import __version__
from localwrite.ui import theme
from localwrite.ui.icons import app_icon
from localwrite.ui.widgets import Card, icon_label, muted_label

if TYPE_CHECKING:
    from localwrite.app_controller import AppController


def _rich(html: str) -> QLabel:
    lbl = QLabel(html)
    lbl.setWordWrap(True)
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setOpenExternalLinks(True)
    lbl.setStyleSheet(f"color: {theme.current().text_soft}; line-height: 150%;")
    return lbl


class AboutPage(QWidget):
    def __init__(self, controller: "AppController") -> None:
        super().__init__()
        self.c = controller
        self.setObjectName("Page")
        p = theme.current()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("PageBody")
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(36, 30, 36, 36)
        lay.setSpacing(18)

        hero = QHBoxLayout()
        hero.setSpacing(18)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(64, 64))
        hero.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(2)
        t = QLabel("LocalWrite")
        t.setObjectName("PageTitle")
        sub = QLabel("A private AI writing assistant for Windows, powered by Ollama.")
        sub.setObjectName("PageSubtitle")
        ver = muted_label(f"Version {__version__} · runs 100% on this computer", small=True)
        names.addWidget(t)
        names.addWidget(sub)
        names.addWidget(ver)
        hero.addLayout(names, 1)
        lay.addLayout(hero)

        how = Card("How it works", "sparkle")
        self.how_label = _rich("")
        how.body.addWidget(self.how_label)
        lay.addWidget(how)

        priv = Card("Our privacy promise", "shield")
        for line in (
            "Your text is processed by Ollama on your own computer and never sent to the internet.",
            "No history: corrections live in memory only and are discarded afterwards.",
            "No keystroke recording. Text is read only when you press a shortcut.",
            "Temporary clipboard copies are hidden from Windows clipboard history and cloud sync.",
            "Logs contain technical events only, never your writing.",
        ):
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(icon_label("check", p.success, 16), 0, Qt.AlignmentFlag.AlignTop)
            lbl = QLabel(line)
            lbl.setWordWrap(True)
            row.addWidget(lbl, 1)
            priv.body.addLayout(row)
        lay.addWidget(priv)

        tr = Card("Troubleshooting", "info")
        tr.body.addWidget(_rich(
            "<p><b>“AI error”</b><br>The local AI didn't answer. Make sure Ollama is running (start it from the "
            "Start menu or run <code>ollama serve</code>) and that the selected model is installed, then press "
            "Retry. A lighter model helps if requests time out. Download Ollama free from "
            "<a style='color:#2f6bff; text-decoration:none' href='https://ollama.com/download/windows'>ollama.com/download/windows</a>.</p>"
            "<p><b>“No text selected”</b><br>Highlight the text first. For slow apps, increase "
            "<i>Wait for selected text</i> in Settings.</p>"
            "<p><b>The text was copied instead of replaced</b><br>The selection changed or the app doesn't allow "
            "pasting. Click where the text should go and press Ctrl+V.</p>"
            "<p><b>An old clipboard item gets pasted</b><br>Increase <i>Wait before restoring</i> in Settings.</p>"
            "<p><b>Nothing happens in an app running as administrator</b><br>Windows blocks input to elevated apps. "
            "Run LocalWrite as administrator too, or use Copy.</p>"
            "<p><b>A shortcut doesn't work</b><br>Another app may already use it. Choose another one in "
            "Settings.</p>"
            "<p><b>Corrections are slow</b><br>Try a lighter model such as <code>qwen2.5:3b</code>. The first "
            "request after starting takes longer while the model loads.</p>"
        ))
        lay.addWidget(tr)
        lay.addStretch(1)

        controller.settings_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        hk = self.c.settings.hotkeys
        self.how_label.setText(
            "<ol style='margin-left:-20px'>"
            "<li>Select text in any app: Chrome, Edge, WhatsApp, Telegram, Discord, Word, Notepad, VS Code, Gmail...</li>"
            f"<li>Press <b>{hk.get('general') or 'your shortcut'}</b> (spelling: <b>{hk.get('spelling') or '-'}</b>, "
            f"professional: <b>{hk.get('professional') or '-'}</b>, quick fix: <b>{hk.get('quick') or '-'}</b>).</li>"
            "<li>Review the suggestion - every change is highlighted.</li>"
            "<li>Click <b>Accept &amp; Replace</b>, or <b>Copy</b>, <b>Retry</b> or pick another writing mode. "
            "Press <b>Esc</b> to close.</li></ol>"
            "<p>Can't select text somewhere (for example a terminal)? Copy it and choose <b>Correct clipboard "
            "text</b> from the tray icon, or paste it into the Writing Assistant.</p>"
        )
