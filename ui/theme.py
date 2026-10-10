#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主题 — 深色（Termius 风格）/ 浅色，两套 Qt 调色板 + QSS"""

DARK = {
    "bg":          "#1a1d24",
    "bg_panel":    "#21252d",
    "bg_input":    "#282d37",
    "bg_hover":    "#2c323d",
    "bg_row":      "#22262e",
    "border":      "#323843",
    "fg":          "#e2e6ea",
    "fg_dim":      "#8a929e",
    "accent":      "#4a9eff",
    "accent_hov":  "#5fadff",
    "accent_fg":   "#ffffff",
    "green":       "#3fb27f",
    "yellow":      "#d9a03f",
    "red":         "#e05561",
    "purple":      "#9d7cd8",
    "gray":        "#6e7681",
    "diff_add_bg": "#12321f",
    "diff_del_bg": "#3a1d20",
    "danger_bg":   "#5a2a2e",
    "danger_hov":  "#6e3338",
    "select_bg":   "#31445c",
}

LIGHT = {
    "bg":          "#f4f5f7",
    "bg_panel":    "#ffffff",
    "bg_input":    "#eef0f3",
    "bg_hover":    "#e3e7ec",
    "bg_row":      "#f7f8fa",
    "border":      "#d8dce2",
    "fg":          "#24292f",
    "fg_dim":      "#6a7280",
    "accent":      "#2563eb",
    "accent_hov":  "#1d4ed8",
    "accent_fg":   "#ffffff",
    "green":       "#15803d",
    "yellow":      "#b45309",
    "red":         "#dc2626",
    "purple":      "#7c3aed",
    "gray":        "#9ca3af",
    "diff_add_bg": "#e6f4ea",
    "diff_del_bg": "#fdeaea",
    "danger_bg":   "#fde3e4",
    "danger_hov":  "#fbd0d2",
    "select_bg":   "#cfe0f7",
}

# 状态码角色 -> 调色板键（models.STATUS_ROLE 里的 "green"/"yellow"… 即这里的键）

FONT_FAMILY = "Noto Sans CJK SC"
MONO_FAMILY = "Noto Sans Mono"

# 勾选框选中态的 ✓ 图标（data URI SVG，跟随 accent_fg 白色）
# 注意: Qt QSS 的 image: url() 不支持 data URI，须用本地文件 —— 启动时写到临时目录
import os as _os
import tempfile as _tempfile

_CHECK_DIR = _os.path.join(_tempfile.gettempdir(), "svn_gui-icons")
_os.makedirs(_CHECK_DIR, exist_ok=True)
CHECK_SVG_PATH = _os.path.join(_CHECK_DIR, "check.svg")
with open(CHECK_SVG_PATH, "w", encoding="utf-8") as _f:
    _f.write(
        "<svg xmlns='http://www.w3.org/2000/svg' width='14' height='14'>"
        "<path d='M2.5 7.5 L6 11 L11.5 3.5' fill='none' stroke='#ffffff' "
        "stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'/>"
        "</svg>"
    )
CHECK_SVG = CHECK_SVG_PATH


class Theme:
    """当前主题状态。App 持有一个实例，组件通过它取色。"""

    def __init__(self, name="dark"):
        self.set(name)

    def set(self, name):
        self.name = name
        self.c = dict(DARK if name == "dark" else LIGHT)

    def color(self, role):
        return self.c.get(role, self.c["fg"])

    # ---------- QSS ----------

    def qss(self):
        c = self.c
        return f"""
* {{
    font-family: "{FONT_FAMILY}";
    font-size: 13px;
}}
QMainWindow, QWidget {{ background: {c['bg']}; color: {c['fg']}; }}
QMenuBar {{ background: {c['bg_panel']}; color: {c['fg']}; border: none; }}
QMenuBar::item {{ background: transparent; padding: 6px 10px; }}
QMenuBar::item:selected {{ background: {c['bg_hover']}; }}
QMenu {{ background: {c['bg_panel']}; color: {c['fg']}; border: 1px solid {c['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {c['bg_hover']}; color: {c['accent']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}

QPushButton {{
    background: {c['bg_input']}; color: {c['fg']};
    border: 1px solid {c['border']}; border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover {{ background: {c['bg_hover']}; }}
QPushButton:disabled {{ color: {c['fg_dim']}; }}
QPushButton#primary {{
    background: {c['accent']}; color: {c['accent_fg']}; border: none; font-weight: bold;
}}
QPushButton#primary:hover {{ background: {c['accent_hov']}; }}
QPushButton#danger {{
    background: {c['danger_bg']}; border: none;
}}
QPushButton#danger:hover {{ background: {c['danger_hov']}; }}
QPushButton#flat {{ background: transparent; border: none; color: {c['fg_dim']}; padding: 4px 10px; }}
QPushButton#flat:hover {{ background: {c['bg_hover']}; color: {c['fg']}; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {c['bg_input']}; color: {c['fg']};
    border: 1px solid {c['border']}; border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {c['select_bg']};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{ border-color: {c['accent']}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {c['bg_panel']}; color: {c['fg']};
    border: 1px solid {c['border']}; selection-background-color: {c['bg_hover']};
    selection-color: {c['accent']};
}}

QTreeWidget, QTreeView, QListWidget, QTableWidget, QTableView {{
    background: {c['bg_panel']}; color: {c['fg']};
    border: none; outline: none;
    alternate-background-color: {c['bg_row']};
}}
QTreeView::item, QTreeWidget::item {{ height: 26px; padding: 0 2px; border-radius: 4px; }}
QTreeView::item:hover, QTreeWidget::item:hover {{ background: {c['bg_hover']}; }}
QTreeView::item:selected, QTreeWidget::item:selected {{ background: {c['select_bg']}; color: {c['fg']}; }}
QHeaderView::section {{
    background: {c['bg_panel']}; color: {c['fg_dim']};
    border: none; border-bottom: 1px solid {c['border']};
    padding: 5px 8px; font-size: 12px;
}}
QTableWidget::item {{ padding: 2px 4px; }}
QTableWidget::item:selected {{ background: {c['select_bg']}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['fg_dim']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 5px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {c['fg_dim']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {c['fg_dim']};
    padding: 8px 16px; border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {c['accent']}; border-bottom: 2px solid {c['accent']}; }}
QTabBar::tab:hover {{ color: {c['fg']}; }}

QLabel#dim {{ color: {c['fg_dim']}; }}
QLabel#title {{ font-size: 15px; font-weight: bold; }}
QLabel#status {{ color: {c['fg_dim']}; font-size: 12px; }}

QProgressBar {{
    background: {c['bg_input']}; border: none; border-radius: 4px; height: 8px;
}}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}

QToolTip {{
    background: {c['bg_panel']}; color: {c['fg']};
    border: 1px solid {c['border']}; padding: 4px;
}}
QDialog {{ background: {c['bg']}; }}
QGroupBox {{
    border: 1px solid {c['border']}; border-radius: 8px;
    margin-top: 12px; padding-top: 8px;
}}
QGroupBox::title {{ color: {c['fg_dim']}; subcontrol-origin: margin; left: 12px; }}
QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator {{
    width: 17px; height: 17px; border: 1px solid {c['border']};
    border-radius: 4px; background: {c['bg_input']};
}}
QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']};
    image: url("{CHECK_SVG}"); }}
"""
