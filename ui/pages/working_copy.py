#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""概览页 — 仓库 URL / 版本 / 变更统计 / 待处理事项（冲突、未版本控制）"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout, QPushButton, QGridLayout,
)

from ...core.repo import current_branch_name


class WorkingCopyPage(QWidget):
    """「概览」标签页: 仓库信息 + 变更状态统计卡片"""

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.theme = main.theme
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        self.info_box = QFrame()
        self.info_lay = QVBoxLayout(self.info_box)
        self.info_lay.setContentsMargins(12, 10, 12, 10)
        lay.addWidget(self.info_box)

        self.stats_box = QFrame()
        self.stats_lay = QGridLayout(self.stats_box)
        self.stats_lay.setContentsMargins(12, 10, 12, 10)
        self.stats_lay.setSpacing(10)
        lay.addWidget(self.stats_box)

        # 副分支快捷卡片
        self.branch_box = QFrame()
        bl = QHBoxLayout(self.branch_box)
        bl.setContentsMargins(12, 10, 12, 10)
        bl.setSpacing(8)
        self.branch_lbl = QLabel("分支: —")
        self.branch_lbl.setStyleSheet("border: none;")
        bl.addWidget(self.branch_lbl, 1)
        btn_side = QPushButton("副分支管理…")
        btn_side.setObjectName("flat")
        btn_side.clicked.connect(self._open_side_branches)
        bl.addWidget(btn_side)
        lay.addWidget(self.branch_box)
        lay.addStretch(1)
        self.apply_theme()
        self.clear()

    def _open_side_branches(self):
        self.main.on_side_branches()

    def apply_theme(self):
        """主题切换时重新套用卡片背景（内联样式不会跟随全局 QSS 更新）"""
        bg = self.theme.c["bg_panel"]
        self.info_box.setStyleSheet(f"QFrame {{ background: {bg}; border-radius: 8px; }}")
        self.stats_box.setStyleSheet(f"QFrame {{ background: {bg}; border-radius: 8px; }}")
        self.branch_box.setStyleSheet(f"QFrame {{ background: {bg}; border-radius: 8px; }}")

    def clear(self):
        self._set_info("未打开工作副本", "")
        self._set_stats({})
        self.branch_lbl.setText("分支: —")

    def _set_info(self, title, sub):
        while self.info_lay.count():
            item = self.info_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        lbl = QLabel(title)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-weight: bold; border: none;")
        self.info_lay.addWidget(lbl)
        if sub:
            s = QLabel(sub)
            s.setObjectName("status")
            s.setWordWrap(True)
            s.setStyleSheet(f"color: {self.theme.c['fg_dim']}; border: none;")
            self.info_lay.addWidget(s)

    def _set_stats(self, counts):
        while self.stats_lay.count():
            item = self.stats_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not counts:
            lbl = QLabel("—")
            lbl.setStyleSheet(f"color: {self.theme.c['fg_dim']}; border: none;")
            self.stats_lay.addWidget(lbl, 0, 0)
            return
        self.apply_theme()
        c = self.theme.c
        role_map = {"M": "yellow", "A": "green", "D": "red", "R": "purple",
                    "C": "red", "!": "red", "?": "gray", "X": "gray", "~": "yellow"}
        desc_map = {"M": "修改", "A": "新增", "D": "删除", "R": "替换",
                    "C": "冲突", "!": "丢失", "?": "未版本控制", "X": "外部", "~": "类型变更"}
        row = col = 0
        for code, n in sorted(counts.items()):
            color = c[role_map.get(code, "fg")]
            box = QLabel(f"{code}  {desc_map.get(code, code)}: {n}")
            box.setStyleSheet(
                f"background: {c['bg_row']}; color: {color}; border-radius: 6px;"
                f"padding: 8px 12px; font-weight: bold;"
            )
            self.stats_lay.addWidget(box, row, col)
            col += 1
            if col >= 2:
                col = 0
                row += 1

    def update_info(self, repo, items):
        if not repo:
            self.clear()
            return
        self.apply_theme()
        try:
            info = repo.info()
        except Exception as e:
            self._set_info("读取仓库信息失败", str(e))
            return
        self._set_info(info.url or repo.path,
                       f"版本 r{info.revision}   ·   {repo.path}")
        br = current_branch_name(info.url)
        self.branch_lbl.setText(f"分支: {br or '（非标准布局，无法识别）'}")
        counts = {}
        for it in items:
            counts[it.code] = counts.get(it.code, 0) + 1
        self._set_stats(counts)
