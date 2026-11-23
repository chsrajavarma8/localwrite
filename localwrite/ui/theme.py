"""The single LocalWrite theme: a premium white/light design.

White surfaces, light-gray secondary backgrounds, soft borders, subtle shadows
and one restrained blue accent. There is intentionally no dark mode.
"""
from __future__ import annotations

from dataclasses import dataclass

from localwrite.core.diff import DiffColors


@dataclass(frozen=True)
class Palette:
    window: str        # main content background (pure white)
    sidebar: str       # light gray navigation background
    surface: str       # cards
    surface_alt: str   # inputs, secondary panels
    hover: str
    border: str
    border_strong: str
    text: str
    text_soft: str
    muted: str
    accent: str
    accent_hover: str
    accent_soft: str
    accent_text: str
    success: str
    success_soft: str
    warning: str
    warning_soft: str
    danger: str
    danger_soft: str
    selection: str
    ins_bg: str
    ins_fg: str
    del_bg: str
    del_fg: str

    @property
    def diff_colors(self) -> DiffColors:
        return DiffColors(self.ins_bg, self.ins_fg, self.del_bg, self.del_fg)


LIGHT = Palette(
    window="#ffffff", sidebar="#f7f8fa", surface="#ffffff", surface_alt="#f8f9fb", hover="#f1f3f6",
    border="#e6e8ec", border_strong="#d5d9e0", text="#151a23", text_soft="#384152", muted="#6b7385",
    accent="#2f6bff", accent_hover="#1f58e6", accent_soft="#eef3ff", accent_text="#ffffff",
    success="#12a05c", success_soft="#e9f7ef", warning="#b7791f", warning_soft="#fff7e8",
    danger="#d63c3c", danger_soft="#fdeeee", selection="#d9e5ff",
    ins_bg="#e3f5ea", ins_fg="#0c6b3a", del_bg="#fdecec", del_fg="#b3261e",
)


def current() -> Palette:
    return LIGHT


def apply_light_mode(app) -> None:
    """Force light mode app-wide, even when Windows itself is in dark mode.

    The stylesheet covers our own widgets, but standard Qt parts (wizard header,
    message boxes, input dialogs, window title bars) draw from the system palette,
    which follows Windows' dark setting. Pin the colour scheme and palette to light.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QGuiApplication, QPalette

    hints = QGuiApplication.styleHints()
    if hasattr(hints, "setColorScheme"):  # Qt 6.8+: also makes window title bars light
        hints.setColorScheme(Qt.ColorScheme.Light)
    p = LIGHT
    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: p.window,
        QPalette.ColorRole.WindowText: p.text,
        QPalette.ColorRole.Base: p.surface,
        QPalette.ColorRole.AlternateBase: p.surface_alt,
        QPalette.ColorRole.Text: p.text,
        QPalette.ColorRole.Button: p.surface,
        QPalette.ColorRole.ButtonText: p.text,
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.Highlight: p.accent,
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: p.surface,
        QPalette.ColorRole.ToolTipText: p.text,
        QPalette.ColorRole.PlaceholderText: "#9aa1ae",
        QPalette.ColorRole.Link: p.accent,
        QPalette.ColorRole.LinkVisited: p.accent,
        QPalette.ColorRole.Light: "#ffffff",
        QPalette.ColorRole.Midlight: p.surface_alt,
        QPalette.ColorRole.Mid: p.border,
        QPalette.ColorRole.Dark: p.border_strong,
        QPalette.ColorRole.Shadow: "#c4c9d2",
    }
    for role, color in roles.items():
        pal.setColor(QPalette.ColorGroup.All, role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor("#a4aab6"))
    app.setPalette(pal)


def stylesheet(p: Palette = LIGHT) -> str:
    return f"""
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif; font-size: 10pt; }}
QWidget {{ color: {p.text}; }}
QMainWindow, QDialog, QWizard, QWizardPage, #Page, #PageBody {{ background: {p.window}; }}
QToolTip {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border}; padding: 6px 8px; border-radius: 6px; }}

/* ---------- navigation ---------- */
#Sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}
#AppTitle {{ font-family: "Segoe UI Variable Display", "Segoe UI"; font-size: 14pt; font-weight: 700; }}
QLabel[muted="true"] {{ color: {p.muted}; }}
QLabel[small="true"] {{ font-size: 9pt; }}
QPushButton[nav="true"] {{
    text-align: left; padding: 9px 12px; border: none; border-radius: 8px; background: transparent;
    color: {p.text_soft}; font-weight: 600;
}}
QPushButton[nav="true"]:hover {{ background: {p.hover}; }}
QPushButton[nav="true"]:checked {{ background: {p.surface}; color: {p.accent}; border: 1px solid {p.border}; }}

/* ---------- typography ---------- */
#PageTitle {{ font-family: "Segoe UI Variable Display", "Segoe UI"; font-size: 20pt; font-weight: 700; }}
#PageSubtitle {{ color: {p.muted}; font-size: 10.5pt; }}
#CardTitle {{ font-size: 11pt; font-weight: 700; }}
#SectionLabel {{ color: {p.muted}; font-size: 8.5pt; font-weight: 700; letter-spacing: 0.6px; }}
#RowTitle {{ font-weight: 600; }}
#BigValue {{ font-size: 12pt; font-weight: 700; }}

/* ---------- surfaces ---------- */
#Card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 14px; }}
#Divider {{ background: {p.border}; max-height: 1px; min-height: 1px; border: none; }}
#Notice {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 12px; }}
#NoticeWarn {{ background: {p.warning_soft}; border: 1px solid #f3dfb8; border-radius: 12px; }}
#NoticeError {{ background: {p.danger_soft}; border: 1px solid #f6d2d2; border-radius: 12px; }}
#NoticeInfo {{ background: {p.accent_soft}; border: 1px solid #d8e3ff; border-radius: 12px; }}
#KeyCap {{
    background: {p.surface}; border: 1px solid {p.border_strong}; border-bottom: 2px solid {p.border_strong};
    border-radius: 6px; padding: 1px 7px; font-family: "Segoe UI"; font-size: 9pt; font-weight: 600; color: {p.text_soft};
}}
QFrame[tile="true"] {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px; }}
QFrame[tile="true"]:hover {{ border-color: {p.border_strong}; background: {p.surface_alt}; }}
QFrame[tile="true"][selected="true"] {{ border: 1px solid {p.accent}; background: {p.accent_soft}; }}

/* ---------- buttons ---------- */
QPushButton {{
    background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: 8px; padding: 7px 14px;
    font-weight: 600; color: {p.text};
}}
QPushButton:hover {{ background: {p.hover}; }}
QPushButton:pressed {{ background: {p.border}; }}
QPushButton:disabled {{ color: #a4aab6; border-color: {p.border}; background: {p.surface_alt}; }}
QPushButton[variant="primary"] {{ background: {p.accent}; color: {p.accent_text}; border: 1px solid {p.accent}; }}
QPushButton[variant="primary"]:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton[variant="primary"]:disabled {{ background: #b9cbf9; border-color: #b9cbf9; color: #ffffff; }}
QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent; color: {p.text_soft}; }}
QPushButton[variant="ghost"]:hover {{ background: {p.hover}; }}
QPushButton[variant="link"] {{ background: transparent; border: none; color: {p.accent}; padding: 2px 0; font-weight: 600; text-align: left; }}
QPushButton[variant="link"]:hover {{ color: {p.accent_hover}; text-decoration: underline; }}
QPushButton[variant="danger"] {{ color: {p.danger}; }}
QPushButton[chip="true"] {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: 15px; padding: 5px 13px; font-weight: 600;
    color: {p.text_soft};
}}
QPushButton[chip="true"]:hover {{ border-color: {p.border_strong}; background: {p.surface_alt}; }}
QPushButton[chip="true"]:checked {{ background: {p.accent_soft}; border-color: {p.accent}; color: {p.accent}; }}
QToolButton {{ background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: 8px; padding: 6px 12px; font-weight: 600; }}
QToolButton:hover {{ background: {p.hover}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton#CloseButton {{ background: transparent; border: none; color: {p.muted}; font-size: 12pt; padding: 2px 6px; border-radius: 6px; }}
QToolButton#CloseButton:hover {{ background: {p.hover}; color: {p.text}; }}

/* ---------- inputs ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QKeySequenceEdit {{
    background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: 8px; padding: 6px 9px;
    selection-background-color: {p.selection}; selection-color: {p.text};
}}
QLineEdit:hover, QPlainTextEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: #c3c9d3; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
QKeySequenceEdit:focus {{ border: 1px solid {p.accent}; }}
QPlainTextEdit#Editor {{ background: {p.surface}; border-radius: 12px; padding: 10px 12px; font-size: 11pt; }}
QTextBrowser {{ background: {p.surface}; border: none; }}
QTextBrowser#DiffView {{
    background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 10px; padding: 6px 8px; font-size: 10.5pt;
}}
QTextBrowser#ResultView {{ background: {p.surface}; border: none; font-size: 11pt; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px; padding: 4px; outline: 0;
    selection-background-color: {p.accent_soft}; selection-color: {p.text};
}}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 17px; height: 17px; border-radius: 5px; border: 1px solid {p.border_strong}; background: {p.surface}; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}

/* ---------- lists / scroll / menus ---------- */
QListWidget {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; outline: 0; padding: 4px; }}
QListWidget::item {{ padding: 8px 10px; border-radius: 7px; }}
QListWidget::item:hover {{ background: {p.hover}; }}
QListWidget::item:selected {{ background: {p.accent_soft}; color: {p.text}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #d3d8e0; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #b9c0cb; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
QScrollBar:horizontal {{ height: 0; }}
QMenu {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 28px 7px 26px; border-radius: 6px; color: {p.text}; }}
QMenu::item:selected {{ background: {p.accent_soft}; color: {p.text}; }}
QMenu::item:disabled {{ color: {p.muted}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 5px 8px; }}
QMenu::indicator {{ width: 8px; height: 8px; left: 10px; }}
QMenu::indicator:checked {{ image: none; background: {p.accent}; border-radius: 4px; width: 8px; height: 8px; left: 10px; }}
QProgressBar {{ background: {p.hover}; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 4px; }}
QSizeGrip {{ background: transparent; width: 14px; height: 14px; }}

/* ---------- popup ---------- */
#PopupFrame {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 16px; }}
#PopupTitle {{ font-size: 10.5pt; font-weight: 700; }}
#Chip {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 10px; padding: 2px 9px; color: {p.muted}; font-size: 8.5pt; }}
#ChipAccent {{ background: {p.accent_soft}; border: 1px solid #d8e3ff; border-radius: 10px; padding: 2px 9px; color: {p.accent}; font-size: 8.5pt; font-weight: 700; }}
#ChipSuccess {{ background: {p.success_soft}; border: 1px solid #cdebd9; border-radius: 10px; padding: 2px 9px; color: {p.success}; font-size: 8.5pt; font-weight: 700; }}
#ErrorTitle {{ color: {p.text}; font-weight: 700; font-size: 10.5pt; }}
#InfoOk {{ color: {p.success}; font-weight: 600; }}
#InfoWarn {{ color: {p.warning}; font-weight: 600; }}
#InfoErr {{ color: {p.danger}; font-weight: 600; }}
#Badge {{ background: {p.accent}; color: {p.accent_text}; border-radius: 12px; padding: 4px 12px; font-weight: 700; }}

QWizard > QWidget {{ background: {p.window}; }}
"""
