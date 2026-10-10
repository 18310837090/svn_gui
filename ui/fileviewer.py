#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件查看器 — 应用内展示文件内容（代替系统文本编辑器）"""

import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QWidget, QLineEdit,
)


# 简单的扩展名 → 语法高亮分类（够用即可，不做完整 lexer）
_CODE_EXTS = {
    ".py", ".java", ".c", ".h", ".cpp", ".hpp", ".cc", ".js", ".ts",
    ".php", ".rb", ".go", ".rs", ".sh", ".bash", ".xml", ".html", ".css",
    ".sql", ".json", ".yaml", ".yml", ".ini", ".cfg", ".conf", ".properties",
    ".jsp", ".vue", ".jsx", ".tsx", ".kt", ".cs", ".pl", ".lua", ".mk", ".md",
}
_TEXT_EXTS = {
    ".txt", ".log", ".csv", ".gitignore", ".svnignore", ".editorconfig",
    ".env", ".list", ".properties", ".gradle", ".pom",
}


class FileViewer(QDialog):
    """在软件内部查看文件内容: 只读、行号、可搜索"""

    def __init__(self, parent, path, theme):
        super().__init__(parent)
        self.theme = theme
        self.path = path
        self.setWindowTitle(f"查看 — {os.path.basename(path)}")
        self.resize(900, 640)

        c = theme.c
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)

        # 顶栏: 路径 + 大小
        bar = QHBoxLayout()
        try:
            size = os.path.getsize(path)
            size_txt = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"
        except OSError:
            size_txt = ""
        title = QLabel(f"{path}   ({size_txt})")
        title.setStyleSheet(f"color: {c['fg_dim']};")
        bar.addWidget(title, 1)
        root.addLayout(bar)

        # 文本区: 行号区 + 内容
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        font = QFont("Noto Sans Mono", 10)
        self.text.setFont(font)
        self.text.setStyleSheet(
            f"QPlainTextEdit {{ background: {c['bg_panel']}; color: {c['fg']};"
            f" border: 1px solid {c['border']}; border-radius: 8px; padding: 8px;"
            f" selection-background-color: {c['select_bg']}; }}"
        )
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text.blockCountChanged.connect(self._update_linenum_width)
        self.text.updateRequest.connect(self._update_linenum_area)

        self.linenum = _LineNumberArea(self.text, c)
        root.addWidget(self.text, 1)

        # 底部: 搜索
        sbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索… (Enter 下一个)")
        self.search.returnPressed.connect(self._find_next)
        sbar.addWidget(self.search, 1)
        btn_next = QPushButton("下一个")
        btn_next.clicked.connect(self._find_next)
        sbar.addWidget(btn_next)
        root.addLayout(sbar)

        self._load()

    # ---------- 内容加载 ----------

    def _load(self):
        """读文件; 二进制文件提示不可预览"""
        try:
            with open(self.path, "rb") as f:
                raw = f.read(8 * 1024 * 1024)   # 最多 8MB
        except OSError as e:
            self.text.setPlainText(f"无法读取文件: {e}")
            return
        if b"\x00" in raw[:4096]:
            self.text.setPlainText("（二进制文件，不支持在软件内预览）")
            return
        enc = "utf-8"
        try:
            content = raw.decode(enc)
        except UnicodeDecodeError:
            try:
                content = raw.decode("gbk")
            except UnicodeDecodeError:
                content = raw.decode("utf-8", errors="replace")
        self.text.setPlainText(content)
        self._update_linenum_width(0)

    # ---------- 行号 ----------

    def _linenum_area_width(self):
        digits = max(2, len(str(max(1, self.text.blockCount()))))
        return 12 + self.text.fontMetrics().horizontalAdvance("9") * digits

    def _update_linenum_width(self, _):
        self.text.setViewportMargins(self._linenum_area_width(), 0, 0, 0)

    def _update_linenum_area(self, rect, dy):
        if dy:
            self.linenum.scroll(0, dy)
        else:
            self.linenum.update(0, rect.y(), self.linenum.width(), rect.height())
        if rect.contains(self.text.viewport().rect()):
            self._update_linenum_width(0)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        cr = self.text.contentsRect()
        self.linenum.setGeometry(cr.left(), cr.top(), self._linenum_area_width(), cr.height())

    # ---------- 搜索 ----------

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


class _LineNumberArea(QWidget):
    """QPlainTextEdit 左侧行号区"""

    def __init__(self, editor, c):
        super().__init__(editor)
        self.editor = editor
        self.c = c

    def sizeHint(self):
        return QSize(0, 0)

    def paintEvent(self, ev):
        from PySide6.QtGui import QPainter
        from PySide6.QtCore import QRect
        painter = QPainter(self)
        painter.fillRect(ev.rect(), QColor(self.c["bg"]))
        block = self.editor.firstVisibleBlock()
        n = block.blockNumber()
        top = round(self.editor.blockBoundingGeometry(block).translated(self.editor.contentOffset()).top())
        bottom = top + round(self.editor.blockBoundingRect(block).height())
        painter.setPen(QColor(self.c["fg_dim"]))
        font = painter.font()
        font.setPointSizeF(self.editor.font().pointSizeF())
        painter.setFont(font)
        while block.isValid() and top <= ev.rect().bottom():
            if block.isVisible() and bottom >= ev.rect().top():
                painter.drawText(0, top, self.width() - 6, self.editor.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight, str(n + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.editor.blockBoundingRect(block).height())
            n += 1
        painter.end()
