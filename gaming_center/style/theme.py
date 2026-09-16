"""Theme constants and unified QSS stylesheet for Gaming Center.

Dark futuristic gaming aesthetics matching CachyOS / Arch Linux desktop styling.
"""

class ThemeColors:
    # Backgrounds
    BG_ROOT = "#0a0e14"
    BG_MAIN = "#0d131b"
    BG_PANEL = "#111823"
    BG_CARD = "#15202e"
    BG_CARD_HOVER = "#1b2a3d"
    BG_CARD_SELECTED = "#1e334a"
    BG_INPUT = "#0c1219"
    BG_TOOLTIP = "#182230"
    
    # Borders
    BORDER_SUBTLE = "#1e293b"
    BORDER_CARD = "#243447"
    BORDER_HOVER = "#38bdf8"
    BORDER_ACTIVE = "#00d494"
    
    # Accents
    ACCENT_GREEN = "#00d494"        # Primary highlight (Emerald)
    ACCENT_CYAN = "#00d2ff"         # Secondary highlight (Cyan)
    ACCENT_PURPLE = "#a855f7"       # Proton / Wiki highlight
    ACCENT_AMBER = "#f59e0b"        # Warning / Highlight
    ACCENT_RED = "#ef4444"          # Danger / Remove
    ACCENT_BLUE = "#3b82f6"         # Steam Blue
    
    # Text
    TEXT_PRIMARY = "#f8fafc"
    TEXT_SECONDARY = "#94a3b8"
    TEXT_MUTED = "#64748b"
    TEXT_ACCENT = "#38bdf8"


APP_STYLESHEET = f"""
/* Global Reset & Base */
QWidget {{
    background-color: transparent;
    color: {ThemeColors.TEXT_PRIMARY};
    font-family: "Inter", "Cantarell", "Noto Sans", "Segoe UI", Roboto, sans-serif;
    font-size: 13px;
    outline: none;
}}

QMainWindow, QDialog {{
    background-color: {ThemeColors.BG_ROOT};
}}

/* Scrollbars */
QScrollBar:vertical {{
    background: {ThemeColors.BG_ROOT};
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {ThemeColors.BORDER_SUBTLE};
    min-height: 30px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ThemeColors.ACCENT_GREEN};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {ThemeColors.BG_ROOT};
    height: 8px;
    margin: 0px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {ThemeColors.BORDER_SUBTLE};
    min-width: 30px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {ThemeColors.ACCENT_GREEN};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* Top Navigation / Toolbar */
#TopBar {{
    background-color: {ThemeColors.BG_MAIN};
    border-bottom: 1px solid {ThemeColors.BORDER_SUBTLE};
    padding: 8px 16px;
}}

#AppTitle {{
    font-size: 18px;
    font-weight: bold;
    color: {ThemeColors.TEXT_PRIMARY};
    letter-spacing: 0.5px;
}}

#AppSubtitle {{
    font-size: 11px;
    color: {ThemeColors.TEXT_SECONDARY};
    font-weight: 500;
}}

/* Search and Input Fields */
QLineEdit {{
    background-color: {ThemeColors.BG_INPUT};
    color: {ThemeColors.TEXT_PRIMARY};
    border: 1px solid {ThemeColors.BORDER_CARD};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: {ThemeColors.ACCENT_GREEN};
    selection-color: #000000;
}}
QLineEdit:hover {{
    border-color: {ThemeColors.BORDER_HOVER};
}}
QLineEdit:focus {{
    border-color: {ThemeColors.ACCENT_GREEN};
    background-color: {ThemeColors.BG_PANEL};
}}

/* Push Buttons */
QPushButton {{
    background-color: {ThemeColors.BG_CARD};
    color: {ThemeColors.TEXT_PRIMARY};
    border: 1px solid {ThemeColors.BORDER_CARD};
    border-radius: 6px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {ThemeColors.BG_CARD_HOVER};
    border-color: {ThemeColors.ACCENT_CYAN};
    color: #ffffff;
}}
QPushButton:pressed {{
    background-color: {ThemeColors.BG_ROOT};
}}
QPushButton:disabled {{
    background-color: rgba(255, 255, 255, 0.03);
    color: {ThemeColors.TEXT_MUTED};
    border-color: transparent;
}}

/* Primary Action Buttons */
QPushButton[class="primary-btn"] {{
    background-color: {ThemeColors.ACCENT_GREEN};
    color: #04100c;
    border: 1px solid {ThemeColors.ACCENT_GREEN};
    font-weight: bold;
}}
QPushButton[class="primary-btn"]:hover {{
    background-color: #00f0a8;
    border-color: #00f0a8;
    color: #000000;
}}
QPushButton[class="primary-btn"]:pressed {{
    background-color: #00b07c;
}}

/* Subtle / Ghost Buttons */
QPushButton[class="ghost-btn"] {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {ThemeColors.TEXT_SECONDARY};
}}
QPushButton[class="ghost-btn"]:hover {{
    background-color: rgba(255, 255, 255, 0.06);
    color: {ThemeColors.TEXT_PRIMARY};
    border-color: {ThemeColors.BORDER_SUBTLE};
}}

/* Danger Buttons */
QPushButton[class="danger-btn"] {{
    background-color: rgba(239, 68, 68, 0.15);
    color: #fca5a5;
    border: 1px solid rgba(239, 68, 68, 0.4);
}}
QPushButton[class="danger-btn"]:hover {{
    background-color: {ThemeColors.ACCENT_RED};
    color: #ffffff;
    border-color: {ThemeColors.ACCENT_RED};
}}

/* Combo Box */
QComboBox {{
    background-color: {ThemeColors.BG_INPUT};
    color: {ThemeColors.TEXT_PRIMARY};
    border: 1px solid {ThemeColors.BORDER_CARD};
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 500;
    min-width: 110px;
}}
QComboBox:hover {{
    border-color: {ThemeColors.BORDER_HOVER};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left-width: 0px;
}}
QComboBox QAbstractItemView {{
    background-color: {ThemeColors.BG_PANEL};
    border: 1px solid {ThemeColors.BORDER_CARD};
    selection-background-color: {ThemeColors.BG_CARD_HOVER};
    selection-color: {ThemeColors.ACCENT_GREEN};
    padding: 4px;
}}

/* Tab Widget & Bar */
QTabWidget::pane {{
    border: 1px solid {ThemeColors.BORDER_SUBTLE};
    background-color: {ThemeColors.BG_MAIN};
    border-radius: 8px;
    top: -1px;
}}
QTabBar::tab {{
    background-color: {ThemeColors.BG_PANEL};
    color: {ThemeColors.TEXT_SECONDARY};
    padding: 10px 18px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 600;
    font-size: 12px;
    border: 1px solid transparent;
}}
QTabBar::tab:hover {{
    background-color: {ThemeColors.BG_CARD};
    color: {ThemeColors.TEXT_PRIMARY};
}}
QTabBar::tab:selected {{
    background-color: {ThemeColors.BG_MAIN};
    color: {ThemeColors.ACCENT_GREEN};
    border: 1px solid {ThemeColors.BORDER_SUBTLE};
    border-bottom: 1px solid {ThemeColors.BG_MAIN};
}}

/* Game Cards */
#GameCard {{
    background-color: {ThemeColors.BG_CARD};
    border: 1px solid {ThemeColors.BORDER_CARD};
    border-radius: 10px;
}}
#GameCard:hover {{
    background-color: {ThemeColors.BG_CARD_HOVER};
    border-color: {ThemeColors.ACCENT_GREEN};
}}

/* Panels and Group Boxes */
QGroupBox {{
    background-color: {ThemeColors.BG_PANEL};
    border: 1px solid {ThemeColors.BORDER_SUBTLE};
    border-radius: 8px;
    margin-top: 24px;
    padding: 16px;
    font-weight: bold;
    color: {ThemeColors.TEXT_PRIMARY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    color: {ThemeColors.ACCENT_GREEN};
}}

/* Badges / Pill Tags */
QLabel[class="badge"] {{
    background-color: rgba(56, 189, 248, 0.12);
    color: {ThemeColors.ACCENT_CYAN};
    border: 1px solid rgba(56, 189, 248, 0.25);
    border-radius: 12px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel[class="badge-success"] {{
    background-color: rgba(0, 212, 148, 0.12);
    color: {ThemeColors.ACCENT_GREEN};
    border: 1px solid rgba(0, 212, 148, 0.3);
}}
QLabel[class="badge-warning"] {{
    background-color: rgba(245, 158, 11, 0.12);
    color: {ThemeColors.ACCENT_AMBER};
    border: 1px solid rgba(245, 158, 11, 0.3);
}}
QLabel[class="badge-purple"] {{
    background-color: rgba(168, 85, 247, 0.12);
    color: {ThemeColors.ACCENT_PURPLE};
    border: 1px solid rgba(168, 85, 247, 0.3);
}}

/* Checkboxes */
QCheckBox {{
    spacing: 8px;
    font-size: 13px;
    color: {ThemeColors.TEXT_PRIMARY};
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid {ThemeColors.BORDER_CARD};
    background-color: {ThemeColors.BG_INPUT};
}}
QCheckBox::indicator:hover {{
    border-color: {ThemeColors.ACCENT_GREEN};
}}
QCheckBox::indicator:checked {{
    background-color: {ThemeColors.ACCENT_GREEN};
    border-color: {ThemeColors.ACCENT_GREEN};
}}

/* Status Bar */
QStatusBar {{
    background-color: {ThemeColors.BG_ROOT};
    color: {ThemeColors.TEXT_MUTED};
    border-top: 1px solid {ThemeColors.BORDER_SUBTLE};
    font-size: 11px;
    padding: 4px 12px;
}}
"""
