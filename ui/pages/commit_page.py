#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提交页 — 模态对话框: 勾选文件（按状态分组）+ 提交说明（模板/历史）+ 提交结果"""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QPlainTextEdit, QComboBox, QMenu,
    QProgressBar, QFrame,
)

from ...core.store import push_history, load_history
from ..diffviewer import DiffViewer


class CommitPage(QDialog):
    """执行提交。do_fn(message, paths) 在后台执行，
    完成后 committed_rev 非 None 表示成功。"""

    def __init__(self, parent, items, repo, theme, auto_update=True):
        super().__init__(parent)
        self.theme = theme
        self.repo = repo
        self.items = items
        self.auto_update = auto_update
        self.committed_rev = None
        self._committing = False

        self.setWindowTitle("提交代码")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.resize(860, 660)

        c = theme.c
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        # 文件树（按状态分组，复选框）
        head = QHBoxLayout()
        head.addWidget(QLabel(f"待提交文件（{len(items)}）"))
        head.addStretch(1)
        self.select_all = QCheckBox("全选")
        self.select_all.toggled.connect(self._toggle_all)
        head.addWidget(self.select_all)
        root.addLayout(head)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.setColumnWidth(0, 620)
        root.addWidget(self.tree, 1)

        groups = {}
        for it in items:
            groups.setdefault(it.code, []).append(it)
        desc = {"M": "修改", "A": "新增", "D": "删除", "R": "替换", "C": "冲突",
                "!": "丢失", "?": "未版本控制", "X": "外部", "~": "类型变更"}
        role_map = {"M": "yellow", "A": "green", "D": "red", "R": "purple",
                    "C": "red", "!": "red", "?": "gray", "X": "gray", "~": "yellow"}
        for code in sorted(groups):
            group = sorted(groups[code], key=lambda x: x.path)
            color = c[role_map.get(code, "fg")]
            gnode = QTreeWidgetItem([f"{desc.get(code, code)} ({len(group)})", ""])
            gnode.setForeground(0, QBrush(QColor(color)))
            self.tree.addTopLevelItem(gnode)
            for it in group:
                node = QTreeWidgetItem([f"{it.name}    ·    {it.dirname}/", it.code])
                node.setCheckState(0, Qt.CheckState.Unchecked)
                node.setData(0, Qt.ItemDataRole.UserRole, it)
                node.setForeground(1, QBrush(QColor(c[role_map.get(it.role, "fg")])))
                gnode.addChild(node)
            gnode.setExpanded(True)
        self.tree.itemChanged.connect(self._on_item_changed)

        # 提交说明
        msg_head = QHBoxLayout()
        msg_head.addWidget(QLabel("提交说明"))
        msg_head.addStretch(1)
        self.template_combo = QComboBox()
        self.template_combo.addItem("模板…")
        from ...core.store import Config
        for t in Config().templates:
            self.template_combo.addItem(t)
        self.template_combo.activated.connect(self._use_template)
        msg_head.addWidget(self.template_combo)
        hist_btn = QPushButton("历史")
        hist_btn.setObjectName("flat")
        hist_btn.clicked.connect(self._show_history)
        msg_head.addWidget(hist_btn)
        root.addLayout(msg_head)

        self.msg_edit = QPlainTextEdit()
        self.msg_edit.setMaximumHeight(100)
        self.msg_edit.keyPressEvent = self._msg_key  # Ctrl+Enter 提交
        # 自定义占位提示: 获得焦点即隐藏（比系统 placeholder 更早消失），失焦且为空时恢复
        self._placeholder = "输入提交说明…（Ctrl+Enter 提交）"
        self._ph_lbl = QLabel(self._placeholder, self.msg_edit.viewport())
        self._ph_lbl.setStyleSheet("color: rgba(128,128,128,0.75); border: none;"
                                   "padding: 3px 6px; background: transparent;")
        self._ph_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._update_placeholder()
        self.msg_edit.cursorPositionChanged.connect(self._update_placeholder)
        self.msg_edit.focusInEvent = self._msg_focus_in
        self.msg_edit.focusOutEvent = self._msg_focus_out
        root.addWidget(self.msg_edit)

        # 结果区
        self.state_lbl = QLabel("")
        root.addWidget(self.state_lbl)
        self.out_text = QPlainTextEdit()
        self.out_text.setReadOnly(True)
        self.out_text.setMaximumHeight(120)
        self.out_text.setStyleSheet(
            f"QPlainTextEdit {{ background: {c['bg_panel']}; color: {c['fg_dim']};"
            f" border-radius: 6px; font-family: 'Noto Sans Mono'; }}"
        )
        self.out_text.hide()
        root.addWidget(self.out_text)

        # 按钮行
        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self.btn_cancel)
        self.btn_commit = QPushButton("提交 (0)")
        self.btn_commit.setObjectName("primary")
        self.btn_commit.setEnabled(False)
        self.btn_commit.clicked.connect(self._do_commit)
        btns.addWidget(self.btn_commit)
        root.addLayout(btns)

        self.msg_edit.setFocus()

    # ---------- 勾选 ----------

    def _selected_paths(self):
        out = []
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            for j in range(g.childCount()):
                node = g.child(j)
                if node.checkState(0) == Qt.CheckState.Checked:
                    out.append(node.data(0, Qt.ItemDataRole.UserRole).path)
        return out

    def _toggle_all(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            for j in range(g.childCount()):
                g.child(j).setCheckState(0, state)

    def _on_item_changed(self, node, _col=0):
        n = len(self._selected_paths())
        self.btn_commit.setText(f"提交 ({n})")
        self.btn_commit.setEnabled(n > 0 and not self._committing)

    def _update_count(self):
        self._on_item_changed(None)

    # ---------- 模板 / 历史 ----------

    def _update_placeholder(self):
        """有文字或有焦点时隐藏占位提示，否则显示"""
        self._ph_lbl.setVisible(not self.msg_edit.toPlainText() and not self.msg_edit.hasFocus())

    def _msg_focus_in(self, event):
        QPlainTextEdit.focusInEvent(self.msg_edit, event)
        self._update_placeholder()

    def _msg_focus_out(self, event):
        QPlainTextEdit.focusOutEvent(self.msg_edit, event)
        self._update_placeholder()

    def _use_template(self, idx):
        if idx <= 0:
            return
        self.msg_edit.setPlainText(self.template_combo.itemText(idx))
        self.msg_edit.moveCursor(self.msg_edit.textCursor().MoveOperation.End)

    def _show_history(self):
        h = load_history()
        menu = QMenu(self)
        for i, t in enumerate(h[:20]):
            preview = t.splitlines()[0][:30] + ("…" if len(t) > 30 else "")
            menu.addAction(f"[{i+1}] {preview}", lambda checked=False, tt=t: self.msg_edit.setPlainText(tt))
        if not h:
            menu.addAction("(空)").setEnabled(False)
        menu.exec(self.cursor().pos())

    def _msg_key(self, event):
        from PySide6.QtGui import QKeyEvent
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier) and event.key() == Qt.Key.Key_Return:
            self._do_commit()
            return
        QPlainTextEdit.keyPressEvent(self.msg_edit, event)

    # ---------- 提交 ----------

    def _do_commit(self):
        if self._committing:
            return
        message = self.msg_edit.toPlainText().strip()
        if not message:
            self.state_lbl.setText("● 请先填写提交说明")
            self.state_lbl.setStyleSheet(f"color: {self.theme.c['yellow']};")
            return
        paths = self._selected_paths()
        if not paths:
            self.state_lbl.setText("● 请先勾选要提交的文件")
            self.state_lbl.setStyleSheet(f"color: {self.theme.c['yellow']};")
            return

        self._committing = True
        self.btn_commit.setEnabled(False)
        self.btn_commit.setText("提交中…")
        self.btn_cancel.setEnabled(False)
        self.state_lbl.setText(f"● 正在提交 {len(paths)} 个文件，请稍候…")
        self.state_lbl.setStyleSheet(f"color: {self.theme.c['yellow']};")
        self.out_text.show()
        self.out_text.setPlainText("svn commit 运行中…\n")

        repo = self.repo
        auto_update = self.auto_update
        unversioned = [it.path for it in self.items
                       if it.path in set(paths) and it.code == "?"]

        def work():
            if unversioned:
                repo.add(unversioned)
            if auto_update:
                repo.update()
            return repo.commit(paths, message)

        main = self.parent()
        main.runner.run(work, on_result=self._on_result, on_error=self._on_error)

    def _on_result(self, rev):
        push_history(self.msg_edit.toPlainText().strip())
        self._committing = False
        self.committed_rev = rev if rev > 0 else None
        # 提交成功：短暂显示结果后自动关闭窗口
        if self.committed_rev:
            from PySide6.QtCore import QTimer
            c = self.theme.c
            self.state_lbl.setText(f"● 提交成功 → r{rev}")
            self.state_lbl.setStyleSheet(f"color: {c['green']}; font-weight: bold;")
            self.btn_commit.setText("已提交")
            self.btn_commit.setEnabled(False)
            self.btn_cancel.setEnabled(False)
            QTimer.singleShot(800, self.accept)   # 稍作停留让用户看到结果
            return
        c = self.theme.c
        self.state_lbl.setText("● 提交完成（未解析版本号）")
        self.state_lbl.setStyleSheet(f"color: {c['green']}; font-weight: bold;")
        self.btn_commit.setText("已提交")
        self.btn_cancel.setText("关闭")

    def _on_error(self, e):
        self._committing = False
        c = self.theme.c
        self.state_lbl.setText("● 提交失败")
        self.state_lbl.setStyleSheet(f"color: {c['red']}; font-weight: bold;")
        text = str(e)
        if "out of date" in text:
            text += "\n提示: 文件版本落后，请先更新再提交。"
        elif "conflict" in text.lower():
            text += "\n提示: 存在冲突，请先解决冲突。"
        self.out_text.setPlainText(text)
        self.btn_commit.setText("重试")
        self.btn_commit.setEnabled(len(self._selected_paths()) > 0)
        self.btn_cancel.setEnabled(True)
