#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""代码区组件 — Pygments 语法高亮 + 行号 + 当前行高亮"""

import os

from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import (
    QColor, QFont, QPainter, QTextCharFormat, QTextCursor, QTextFormat,
)
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

try:
    from pygments import lex
    from pygments.lexers import get_lexer_for_filename, TextLexer
    from pygments.util import ClassNotFound
    from pygments.token import Token
    _HAS_PYGMENTS = True
except ImportError:
    _HAS_PYGMENTS = False

# 语言 → 按扩展名推断（Pygments 本身支持，这里直接用 get_lexer_for_filename）

# Pygments token 类型 → 颜色（深色/浅色主题各一套，VS Code 风格）
_DARK_COLORS = {
    Token.Keyword: "#c586c0",
    Token.Keyword.Constant: "#569cd6",
    Token.Keyword.Type: "#4ec9b0",
    Token.Name.Class: "#4ec9b0",
    Token.Name.Function: "#dcdcaa",
    Token.Name.Tag: "#569cd6",
    Token.Name.Attribute: "#9cdcfe",
    Token.Name.Builtin: "#4fc1ff",
    Token.Name.Decorator: "#dcdcaa",
    Token.Name.Exception: "#4ec9b0",
    Token.Name.Constant: "#b5cea8",
    Token.Name.Label: "#c8c8c8",
    Token.Literal.String: "#ce9178",
    Token.Literal.Number: "#b5cea8",
    Token.Comment: "#6a9955",
    Token.Operator: "#d4d4d4",
    Token.Generic.Inserted: "#81c995",
    Token.Generic.Deleted: "#f14c4c",
    Token.Generic.Emph: "#d4d4d4",
    Token.Generic.Heading: "#569cd6",
    Token.Generic.Subheading: "#569cd6",
    Token.Generic.Strong: "#d4d4d4",
}
_LIGHT_COLORS = {
    Token.Keyword: "#af00db",
    Token.Keyword.Constant: "#0000ff",
    Token.Keyword.Type: "#267f99",
    Token.Name.Class: "#267f99",
    Token.Name.Function: "#795e26",
    Token.Name.Tag: "#800000",
    Token.Name.Attribute: "#e50000",
    Token.Name.Builtin: "#0000ff",
    Token.Name.Decorator: "#795e26",
    Token.Name.Exception: "#267f99",
    Token.Name.Constant: "#098658",
    Token.Name.Label: "#000000",
    Token.Literal.String: "#a31515",
    Token.Literal.Number: "#098658",
    Token.Comment: "#008000",
    Token.Operator: "#000000",
    Token.Generic.Inserted: "#188038",
    Token.Generic.Deleted: "#c41a16",
    Token.Generic.Emph: "#000000",
    Token.Generic.Heading: "#0000ff",
    Token.Generic.Subheading: "#0000ff",
    Token.Generic.Strong: "#000000",
}


class _PygmentsHighlighter:
    """把 Pygments 的 token 流转成 QTextCharFormat 着色"""

    def __init__(self, theme):
        self.theme = theme
        self.set_theme(theme)

    def set_theme(self, theme):
        self.theme = theme
        dark = theme.name == "dark"
        self._colors = dict(_DARK_COLORS if dark else _LIGHT_COLORS)
        self._fg_default = theme.c["fg"]

    def _fmt(self, color, italic=False, bold=False):
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if italic:
            f.setFontItalic(True)
        if bold:
            f.setFontWeight(QFont.Weight.Bold)
        return f

    def color_for(self, ttype):
        """沿 token 继承链找颜色"""
        while ttype is not None:
            if ttype in self._colors:
                return self._colors[ttype]
            ttype = ttype.parent
        return self._fg_default

    def highlight_block(self, text, lexer):
        """对一段文本返回 [(start, length, QTextCharFormat)]"""
        out = []
        if not _HAS_PYGMENTS or lexer is None:
            return out
        pos = 0
        for ttype, value in lex(text, lexer):
            n = len(value)
            color = self.color_for(ttype)
            italic = bool(ttype in Token.Comment or ttype in Token.Generic.Emph)
            bold = bool(ttype in Token.Generic.Strong or ttype in Token.Generic.Heading)
            out.append((pos, n, self._fmt(color, italic, bold)))
            pos += n
        return out


class CodeView(QPlainTextEdit):
    """只读代码查看器: 行号 + Pygments 语法高亮 + 当前行高亮"""

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setReadOnly(True)
        self.setFont(QFont("Noto Sans Mono", 10))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setCursorWidth(0)
        self._lexer = None
        self._last_text = None
        self._highlighter = _PygmentsHighlighter(theme)
        self._apply_theme()

        # 行号区
        self._linenum = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_linenum_width)
        self.updateRequest.connect(self._update_linenum_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_linenum_width(0)

    # ---------- 主题 ----------

    def apply_theme(self, theme):
        self.theme = theme
        self._highlighter.set_theme(theme)
        self._apply_theme()
        self._linenum.c = theme.c
        self._highlight_current_line()
        # 已渲染的文本颜色是烧进格式里的，需要重新渲染才能换色
        if self._last_text is not None:
            self._render(self._last_text)

    def _apply_theme(self):
        c = self.theme.c
        self.setStyleSheet(
            f"QPlainTextEdit {{ background: {c['bg_panel']};"
            f" color: {c['fg']}; border: 1px solid {c['border']};"
            f" border-radius: 8px; padding: 8px; }}"
        )

    # ---------- 加载内容 ----------

    def set_content(self, text, path=""):
        """设置内容并按文件路径选择 lexer"""
        self._lexer = None
        if _HAS_PYGMENTS and path:
            try:
                self._lexer = get_lexer_for_filename(os.path.basename(path))
            except ClassNotFound:
                self._lexer = None
        if self._lexer is None and _HAS_PYGMENTS:
            self._lexer = TextLexer()
        # 分块渲染: 大文件只在必要时高亮
        self._last_text = text
        self._render(text)

    def _render(self, text):
        """逐块渲染带高亮的文本（QTextCursor 追加格式）"""
        c = self.theme.c
        self.setPlainText("")
        cursor = self.textCursor()
        cursor.beginEditBlock()
        default_fmt = QTextCharFormat()
        default_fmt.setForeground(QColor(c["fg"]))
        if self._lexer is None or not _HAS_PYGMENTS:
            cursor.insertText(text, default_fmt)
        else:
            pos = 0
            n_total = len(text)
            for start, length, fmt in self._highlighter.highlight_block(text, self._lexer):
                if start > pos:
                    cursor.insertText(text[pos:start], default_fmt)
                cursor.insertText(text[start:start + length], fmt)
                pos = start + length
            if pos < n_total:
                cursor.insertText(text[pos:], default_fmt)
        cursor.endEditBlock()
        self.moveCursor(QTextCursor.MoveOperation.Start)

    # ---------- 行号 ----------

    def _linenum_area_width(self):
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_linenum_width(self, _):
        self.setViewportMargins(self._linenum_area_width(), 0, 0, 0)

    def _update_linenum_area(self, rect, dy):
        if dy:
            self._linenum.scroll(0, dy)
        else:
            self._linenum.update(0, rect.y(), self._linenum.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_linenum_width(0)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        cr = self.contentsRect()
        self._linenum.setGeometry(cr.left(), cr.top(),
                                  self._linenum_area_width(), cr.height())

    # ---------- 当前行高亮 ----------

    def _highlight_current_line(self):
        if not self.isReadOnly():
            return
        sel = QTextEdit.ExtraSelection()
        line_color = (QColor(255, 255, 255, 14) if self.theme.name == "dark"
                      else QColor(0, 0, 0, 14))
        sel.format.setBackground(line_color)
        sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        self.setExtraSelections([sel])


class _LineNumberArea(QWidget):
    """CodeView 左侧行号区"""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.c = editor.theme.c

    def sizeHint(self):
        return QSize(self.editor._linenum_area_width(), 0)

    def paintEvent(self, ev):
        painter = QPainter(self)
        c = self.c
        painter.fillRect(ev.rect(), QColor(c["bg"]))
        cur_line = self.editor.textCursor().blockNumber()
        block = self.editor.firstVisibleBlock()
        n = block.blockNumber()
        top = round(self.editor.blockBoundingGeometry(block)
                    .translated(self.editor.contentOffset()).top())
        bottom = top + round(self.editor.blockBoundingRect(block).height())
        painter.setPen(QColor(c["fg_dim"]))
        fm = self.editor.fontMetrics()
        while block.isValid() and top <= ev.rect().bottom():
            if block.isVisible() and bottom >= ev.rect().top():
                if n == cur_line:
                    painter.setPen(QColor(c["accent"]))
                    painter.drawText(0, top, self.width() - 6, fm.height(),
                                     Qt.AlignmentFlag.AlignRight, str(n + 1))
                    painter.setPen(QColor(c["fg_dim"]))
                else:
                    painter.drawText(0, top, self.width() - 6, fm.height(),
                                     Qt.AlignmentFlag.AlignRight, str(n + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.editor.blockBoundingRect(block).height())
            n += 1
        painter.end()
