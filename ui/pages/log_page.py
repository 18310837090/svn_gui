#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提交日志页 — 可滚动的提交历史列表，支持查看单条变更文件与版本间 diff"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QPushButton, QMenu, QInputDialog, QLineEdit,
)

from ...core.models import LogEntry


class LogPage(QWidget):
    """「提交日志」标签页: 结构化日志列表（右键可比对任意两个版本）"""

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.theme = main.theme
        self.entries = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(4)

        head = QHBoxLayout()
        self.title_lbl = QLabel("最近提交")
        self.title_lbl.setStyleSheet("font-weight: bold;")
        head.addWidget(self.title_lbl)
        head.addStretch(1)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("flat")
        refresh_btn.clicked.connect(self.reload)
        head.addWidget(refresh_btn)
        lay.addLayout(head)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["版本", "作者", "日期", "说明"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_menu)
        self.tree.setColumnWidth(0, 70)
        self.tree.setColumnWidth(1, 110)
        self.tree.setColumnWidth(2, 150)
        lay.addWidget(self.tree, 1)

    def load(self, repo):
        self.repo = repo
        self.reload()

    def clear(self):
        """清空列表（打开非工作副本目录时调用）"""
        self.entries = []
        self.tree.clear()
        if hasattr(self, "repo"):
            del self.repo
        self.title_lbl.setText("最近提交")

    def reload(self):
        repo = getattr(self, "repo", None)
        if not repo:
            return
        self.tree.clear()
        self.title_lbl.setText("加载日志中…")
        main = self.main

        def work():
            return repo.log(100)

        def done(entries):
            self.entries = entries
            self._fill()
            self.title_lbl.setText(f"最近提交（{len(entries)}）")

        def fail(e):
            self.title_lbl.setText("日志加载失败")
            main.set_status(f"日志加载失败: {e}")

        main.runner.run(work, on_result=done, on_error=fail)

    def _fill(self):
        c = self.theme.c
        self.tree.clear()
        for e in self.entries:
            node = QTreeWidgetItem([f"r{e.revision}", e.author, e.date, e.message.splitlines()[0] if e.message else ""])
            node.setData(0, Qt.ItemDataRole.UserRole, e)
            node.setToolTip(3, e.message)
            self.tree.addTopLevelItem(node)
            for action, path in e.changed_paths[:8]:
                child = QTreeWidgetItem(["", "", f"{action}", path])
                child.setForeground(3, QBrush(QColor(c["fg_dim"])))
                node.addChild(child)

    def _on_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        e = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(e, LogEntry):
            return
        menu = QMenu(self)
        menu.addAction(f"与工作副本比对 (r{e.revision} → BASE)",
                       lambda: self._diff_range(e.revision, "BASE"))
        menu.addAction(f"与上一版本比对 (r{e.revision-1} → r{e.revision})",
                       lambda: self._diff_range(e.revision - 1, e.revision))
        menu.addSeparator()
        menu.addAction("复制提交说明", lambda: self._copy_message(e))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _diff_range(self, a, b):
        repo = self.repo
        main = self.main

        def work():
            text = repo.diff(rev_from=str(a), rev_to=str(b))
            return repo.parse_diff(text)

        def done(files):
            from ..diffviewer import DiffViewer
            DiffViewer(main, f"Diff r{a} → r{b}", files, self.theme).show()

        main.runner.run(work, on_result=done, on_error=lambda e: main.alert("Diff 失败", str(e)))

    def _copy_message(self, e):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(e.message)
        self.main.set_status("提交说明已复制")
