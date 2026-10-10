#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解决冲突页 — 列出冲突文件，逐个选择解决方式（mine/theirs/working/编辑后标记）"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QComboBox, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush


class ResolvePage(QDialog):
    """对每个冲突文件选择 --accept 策略后执行 svn resolve"""

    STRATEGIES = [
        ("working", "保留工作副本（手动已改，标记已解决）"),
        ("mine-full", "用我的版本（提交前本地的修改）"),
        ("theirs-full", "用仓库版本（update 下来的修改）"),
        ("base", "用基础版本（更新前的共同祖先）"),
    ]

    def __init__(self, parent, repo, conflicts, theme, on_done=None):
        super().__init__(parent)
        self.theme = theme
        self.repo = repo
        self.conflicts = conflicts
        self.on_done = on_done
        self.setWindowTitle("解决冲突")
        self.resize(700, 420)

        c = theme.c
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)
        root.addWidget(QLabel(f"共 {len(conflicts)} 个冲突文件，为每个文件选择解决方式："))

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["文件", "解决方式"])
        self.tree.setColumnWidth(0, 420)
        root.addWidget(self.tree, 1)

        for it in conflicts:
            node = QTreeWidgetItem([it.path, ""])
            node.setData(0, Qt.ItemDataRole.UserRole, it)
            self.tree.addTopLevelItem(node)
            combo = QComboBox()
            for i, (_k, label) in enumerate(self.STRATEGIES):
                combo.addItem(label, _k)
            combo.setCurrentIndex(0)
            self.tree.setItemWidget(node, 1, combo)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btn_ok = QPushButton("执行解决")
        btn_ok.setObjectName("primary")
        btn_ok.clicked.connect(self._run)
        btns.addWidget(btn_ok)
        root.addLayout(btns)

    def _run(self):
        jobs = []
        for i in range(self.tree.topLevelItemCount()):
            node = self.tree.topLevelItem(i)
            combo = self.tree.itemWidget(node, 1)
            it = node.data(0, Qt.ItemDataRole.UserRole)
            jobs.append((it.path, combo.currentData()))

        repo = self.repo

        def work():
            results = []
            for path, accept in jobs:
                try:
                    repo.resolve(path, accept)
                    results.append((path, None))
                except Exception as e:
                    results.append((path, str(e)))
            return results

        def done(results):
            failed = [r for r in results if r[1]]
            if failed:
                self.parent().alert("解决冲突", "部分失败:\n" + "\n".join(f"{p}: {e}" for p, e in failed))
            else:
                self.parent().set_status("冲突已解决，请刷新后确认状态")
            if self.on_done and not failed:
                self.on_done("解决冲突")
            self.accept()

        self.parent().runner.run(work, on_result=done,
                                 on_error=lambda e: self.parent().alert("解决冲突失败", str(e)))
