"""Icosele Vault design tokens — dark palette only."""

FONT_FAMILY = '"Inter", "SF Pro Display", "Segoe UI", sans-serif'

# -- Palette --
BG_DEEP = "#1c1f1e"
BG_PANEL = "#222625"
BG_CARD = "#282d2b"
BG_ELEVATED = "#2e3432"
BORDER = "#3a4240"
BORDER_ACTIVE = "#4caf7d"

ACCENT = "#4caf7d"
ACCENT_LIGHT = "#6ec99a"
ACCENT_DARK = "#357a55"

TEXT_PRIMARY = "#e8ede9"
TEXT_SECONDARY = "#8a9e90"
TEXT_MUTED = "#546058"
TEXT_ON_ACCENT = "#0f1a12"

STOP_RED = "#c0392b"
SUCCESS = "#4caf7d"
WARNING = "#e6a817"

# Legacy aliases
BG = BG_PANEL
CARD_BG = BG_CARD
ELEVATED = BG_ELEVATED
SURFACE = BORDER
SIDEBAR_BG = BG_DEEP
ACCENT_SEC = ACCENT_LIGHT
ACCENT_HOVER = ACCENT_LIGHT
TEXT = TEXT_PRIMARY
TEXT_SEC = TEXT_SECONDARY
TEXT_DIM = TEXT_SECONDARY
TEXT_WHITE = TEXT_PRIMARY
TEXT_OLIVE = TEXT_MUTED
DANGER = STOP_RED
RED = STOP_RED
GREEN = SUCCESS
YELLOW = WARNING
SURFACE2 = BORDER
OVERLAY = TEXT_MUTED

# -- Style fragments --

COMBO_STYLE = f"""
QComboBox {{
    background-color: {BG_CARD}; color: {TEXT_PRIMARY};
    border: 1px solid {BORDER}; border-radius: 6px;
    padding: 8px 12px; font-size: 13px; font-family: {FONT_FAMILY};
}}
QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background-color: {BG_CARD}; color: {TEXT_PRIMARY};
    border: 1px solid {BORDER}; selection-background-color: {BG_ELEVATED};
    outline: none;
}}
"""

INPUT_STYLE = f"""
QLineEdit, QSpinBox {{
    background-color: {BG_CARD}; color: {TEXT_PRIMARY};
    border: 1px solid {BORDER}; border-radius: 6px;
    padding: 8px; font-size: 13px; font-family: {FONT_FAMILY};
}}
QLineEdit:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
"""

TAB_STYLE = f"""
QTabWidget {{ border: none; border-top: none; margin-top: 0px; }}
QTabWidget::pane {{ border: none; border-top: none; margin-top: 0px; background-color: {BG_PANEL}; }}
QTabBar {{ background: transparent; border: none; border-top: none; margin-top: 0px; }}
QTabBar::tab {{
    background-color: transparent; color: {TEXT_SECONDARY};
    border: none; border-top: none; border-bottom: 2px solid transparent;
    padding: 16px 24px; font-size: 13px; font-weight: 500;
    font-family: {FONT_FAMILY}; margin: 0 2px; margin-top: 0px;
}}
QTabBar::tab:selected {{
    color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 600;
    border: none; border-top: none;
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{ color: {ACCENT_LIGHT}; }}
"""

TREE_STYLE = f"""
QTreeWidget {{
    background: {BG_CARD}; border: 1px solid {BORDER};
    border-radius: 6px; color: {TEXT_PRIMARY}; font-size: 12px; outline: 0;
}}
QTreeWidget::item {{ padding: 5px 8px; }}
QTreeWidget::item:selected {{ background-color: {BG_ELEVATED}; color: {TEXT_PRIMARY}; }}
QHeaderView::section {{
    background: {BG_CARD}; color: {TEXT_MUTED};
    border: none; border-bottom: 1px solid {BORDER};
    padding: 6px 10px; font-size: 11px; font-weight: 600;
}}
"""

GPU_TREE_STYLE = TREE_STYLE

LIST_STYLE = f"""
QListWidget {{
    background: {BG_CARD}; border: 1px solid {BORDER};
    border-radius: 6px; color: {TEXT_PRIMARY}; font-size: 12px; outline: none;
}}
QListWidget::item {{ padding: 8px 12px; }}
QListWidget::item:selected {{ background-color: {BG_ELEVATED}; color: {TEXT_PRIMARY}; }}
"""

LABEL_STYLE = f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"
SECTION_LABEL_STYLE = (
    f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 700;"
    f" letter-spacing: 1.5px; background: transparent;"
)


def primary_btn_style() -> str:
    return f"""
        QPushButton {{
            background-color: {ACCENT}; color: {TEXT_ON_ACCENT};
            border: none; border-radius: 10px; padding: 10px;
            font-size: 13px; font-weight: 800; font-family: {FONT_FAMILY};
        }}
        QPushButton:hover {{ background-color: {ACCENT_LIGHT}; }}
        QPushButton:disabled {{ background-color: {BORDER}; color: {TEXT_MUTED}; }}
    """


def secondary_btn_style() -> str:
    return f"""
        QPushButton {{
            background-color: transparent; color: {TEXT_SECONDARY};
            border: 1px solid {BORDER}; border-radius: 6px;
            padding: 0 24px; font-size: 13px; font-weight: 600; font-family: {FONT_FAMILY};
        }}
        QPushButton:hover {{ color: {TEXT_PRIMARY}; border-color: {ACCENT}; }}
        QPushButton:disabled {{ color: {TEXT_MUTED}; border-color: {BORDER}; }}
    """


def save_btn_style() -> str:
    return f"""
        QPushButton {{
            background-color: {ACCENT}; color: {TEXT_ON_ACCENT};
            border: none; border-radius: 6px; padding: 8px 12px;
            font-size: 12px; font-weight: 600; font-family: {FONT_FAMILY};
            min-width: 120px; min-height: 36px;
        }}
        QPushButton:hover {{ background-color: {ACCENT_LIGHT}; }}
    """


def subtle_btn_style() -> str:
    return f"""
        QPushButton {{
            background-color: transparent; color: {TEXT_SECONDARY};
            border: 1px solid {BORDER}; border-radius: 6px;
            padding: 6px 14px; font-size: 12px; font-weight: 600; font-family: {FONT_FAMILY};
        }}
        QPushButton:hover {{ color: {TEXT_PRIMARY}; border-color: {ACCENT}; }}
        QPushButton:disabled {{ color: {TEXT_MUTED}; border-color: {BORDER}; }}
    """


