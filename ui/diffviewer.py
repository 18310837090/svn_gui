#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diff 查看器 — 统一的深色 diff 展示组件（+/- 符号标注，支持文件分段导航）"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCharFormat, QColor, QTextCursor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QComboBox, QLineEdit, QWidget,
)


class DiffViewer(QDialog):
    """展示一个或多个文件的 diff。files: [DiffFile]，theme: Theme"""

    def __init__(self, parent, title, files, theme, cwd=None, external_diff_cmd=""):
        super().__init__(parent)
        self.theme = theme
        self.files = files
        self.cwd = cwd
        self.external_diff_cmd = external_diff_cmd
        self.setWindowTitle(title)
        self.resize(980, 680)

        c = theme.c
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)

        # 顶栏: 文件下拉 + 计数
        bar = QHBoxLayout()
        self.file_combo = QComboBox()
        self.file_combo.setMinimumWidth(360)
        self.file_combo.currentIndexChanged.connect(self._goto_file)
        bar.addWidget(self.file_combo)
        bar.addStretch(1)
        self.added_label = QLabel()
        self.added_label.setStyleSheet(f"color: {c['green']}; font-weight: bold;")
        self.removed_label = QLabel()
        self.removed_label.setStyleSheet(f"color: {c['red']}; font-weight: bold;")
        bar.addWidget(self.added_label)
        bar.addWidget(self.removed_label)
        root.addLayout(bar)

        # 文本区
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont("Noto Sans Mono", 10))
        self.text.setStyleSheet(
            f"QPlainTextEdit {{ background: {c['bg_panel']}; color: {c['fg']};"
            f" border: 1px solid {c['border']}; border-radius: 8px; padding: 8px;"
            f" selection-background-color: {c['select_bg']}; }}"
        )
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        root.addWidget(self.text, 1)

        # 搜索栏
        sbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索… (Enter 下一个)")
        self.search.returnPressed.connect(self._find_next)
        sbar.addWidget(self.search, 1)
        btn_next = QPushButton("下一个")
        btn_next.clicked.connect(self._find_next)
        sbar.addWidget(btn_next)
        root.addLayout(sbar)

        self._render()
        for i, f in enumerate(files):
            self.file_combo.addItem(f.path or f"(file {i+1})", i)
        self._stats()

    # ---------- 渲染 ----------

    def _render(self):
        """逐行渲染: 每行前面加 +/- 符号列，加行绿底、删行红底、上下文普通。
        svn 统一 diff 本身带 +/- 前缀，这里规范化为「符号 + 正文」两段式，
        符号列固定宽度着色加粗，正文干净可读。"""
        c = self.theme.c
        self.text.clear()
        cursor = self.text.textCursor()
        fmt_cache = {}

        def fmt(fg=None, bg=None, bold=False):
            key = (fg, bg, bold)
            if key not in fmt_cache:
                f = QTextCharFormat()
                if fg:
                    f.setForeground(QColor(fg))
                if bg:
                    f.setBackground(QColor(bg))
                if bold:
                    f.setFontWeight(QFont.Weight.Bold)
                fmt_cache[key] = f
            return fmt_cache[key]

        # 符号列样式（加粗、按增/删着色）
        sym_add = fmt(c["green"], c["diff_add_bg"], bold=True)
        sym_del = fmt(c["red"], c["diff_del_bg"], bold=True)
        body_add = fmt(c["fg"], c["diff_add_bg"])
        body_del = fmt(c["fg"], c["diff_del_bg"])
        sym_ctx = fmt(c["fg_dim"])
        body_ctx = fmt(c["fg"])
        styles = {
            "hunk": fmt(c["purple"]),
            "head": fmt(c["fg_dim"]),
            "meta": fmt(c["accent"], bold=True),
        }

        for f in self.files:
            for tag, line in f.lines:
                if tag in styles:
                    cursor.insertText(line + "\n", styles[tag])
                    continue
                # 统一 diff 行首符号: +/−/空格
                if tag == "add" or (line.startswith("+") and not line.startswith("+++")):
                    sign, body, sf, bf = "+", line[1:] if line.startswith("+") else line, sym_add, body_add
                elif tag == "del" or (line.startswith("-") and not line.startswith("---")):
                    sign, body, sf, bf = "−", line[1:] if line.startswith("-") else line, sym_del, body_del
                else:
                    sign, body, sf, bf = " ", line, sym_ctx, body_ctx
                cursor.insertText(f" {sign} ", sf)
                cursor.insertText(body + "\n", bf)
        self.text.moveCursor(QTextCursor.MoveOperation.Start)

    def _stats(self):
        add = sum(1 for f in self.files for tag, _ in f.lines if tag == "add")
        rem = sum(1 for f in self.files for tag, _ in f.lines if tag == "del")
        self.added_label.setText(f"+{add} 新增行")
        self.removed_label.setText(f"−{rem} 删除行")

    # ---------- 导航 / 搜索 ----------

    def _goto_file(self, idx):
        path = self.file_combo.itemData(idx)
        if path is None or not self.files:
            return
        f = self.files[path]
        # 找该文件第一行的位置: 用 Index: 文本搜索
        doc = self.text.document()
        hit = doc.find(f"Index: {f.path}", 0)
        if not hit.isNull():
            self.text.setTextCursor(hit)
            self.text.centerCursor()

    def _find_next(self):
        s = self.search.text()
        if not s:
            return
        doc = self.text.document()
        hit = doc.find(s, self.text.textCursor())
        if hit.isNull():
            hit = doc.find(s, 0)  # 回绕
        if not hit.isNull():
            self.text.setTextCursor(hit)
