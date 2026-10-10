#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""副分支管理页 — 列出 branches/ 下的分支，支持新建 / 切换 / 合并 / 删除"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QLineEdit, QFrame, QHeaderView,
)

from ...core.repo import (
    branches_base, current_branch_name, infer_branch_target,
)


def _valid_name(name):
    return bool(name) and " " not in name and "/" not in name and "\\" not in name


class SideBranchPage(QWidget):
    """「副分支」标签页：branches/ 列表 + 新建 / 切换 / 合并 / 删除"""

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.theme = main.theme
        self._base_url = ""      # branches/ 基目录
        self._cur_url = ""
        self._repo_root = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # 顶部：当前位置 + 新建行
        top = QFrame()
        tv = QVBoxLayout(top)
        tv.setContentsMargins(12, 10, 12, 10)
        tv.setSpacing(8)
        self.pos_lbl = QLabel("未打开工作副本")
        self.pos_lbl.setWordWrap(True)
        tv.addWidget(self.pos_lbl)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(QLabel("名字"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("如 my-experiment")
        self.name_edit.returnPressed.connect(self.on_create)
        row.addWidget(self.name_edit, 1)
        self.btn_create = QPushButton("新建副分支")
        self.btn_create.setObjectName("primary")
        self.btn_create.clicked.connect(self.on_create)
        row.addWidget(self.btn_create)
        tv.addLayout(row)
        lay.addWidget(top)

        # 列表
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["分支", "最后版本", "作者", "时间"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.itemDoubleClicked.connect(lambda *_: self.on_switch())
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.tree, 1)

        # 底部操作行
        ops = QHBoxLayout()
        ops.setSpacing(6)
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.reload)
        ops.addWidget(self.btn_refresh)
        self.btn_switch = QPushButton("切换到此分支")
        self.btn_switch.clicked.connect(self.on_switch)
        ops.addWidget(self.btn_switch)
        self.btn_merge = QPushButton("合并到当前位置…")
        self.btn_merge.clicked.connect(self.on_merge)
        ops.addWidget(self.btn_merge)
        ops.addStretch(1)
        self.btn_delete = QPushButton("删除")
        self.btn_delete.setObjectName("danger")
        self.btn_delete.clicked.connect(self.on_delete)
        ops.addWidget(self.btn_delete)
        lay.addLayout(ops)

        self.state_lbl = QLabel("")
        lay.addWidget(self.state_lbl)
        self.apply_theme()
        self.clear()

    # ---------- 主题 ----------

    def apply_theme(self):
        c = self.theme.c
        self.tree.setStyleSheet(
            f"QTreeWidget {{ background: {c['bg_panel']}; color: {c['fg']};"
            f" border: 1px solid {c['border']}; border-radius: 6px; }}")
        top_bg = c["bg_panel"]
        for w in self.findChildren(QFrame):
            w.setStyleSheet(f"QFrame {{ background: {top_bg}; border-radius: 8px; }}")

    def clear(self):
        self.pos_lbl.setText("未打开工作副本")
        self.tree.clear()
        self.name_edit.setEnabled(False)
        for b in (self.btn_create, self.btn_switch, self.btn_merge, self.btn_delete, self.btn_refresh):
            b.setEnabled(False)

    # ---------- 数据 ----------

    def load(self, repo):
        self.repo = repo
        self.reload()

    def reload(self):
        repo = getattr(self, "repo", None)
        if not repo:
            self.clear()
            return
        try:
            info = repo.info()
        except Exception as e:
            self.pos_lbl.setText(f"读取仓库信息失败: {e}")
            return
        self._cur_url = info.url or ""
        self._repo_root = info.root or ""
        self._base_url = branches_base(self._cur_url, self._repo_root)
        cur_name = current_branch_name(self._cur_url) or "(非标准布局)"
        self.pos_lbl.setText(f"当前位置: {cur_name}   ·   {self._cur_url}")
        self.name_edit.setEnabled(True)
        for b in (self.btn_create, self.btn_refresh):
            b.setEnabled(True)

        main = self.main
        base, repo_ref = self._base_url, repo

        def work():
            return repo_ref.ls_remote(base)

        def done(items):
            self._fill(items)

        def fail(e):
            self.tree.clear()
            QTreeWidgetItem(self.tree, ["(branches/ 不存在或无法访问)", "", "", ""])
            self.state_lbl.setText(str(e))

        main.runner.run(work, on_result=done, on_error=fail)

    def _fill(self, items):
        self.tree.clear()
        c = self.theme.c
        cur_name = current_branch_name(self._cur_url)
        for name, rev, author, date in sorted(items):
            it = QTreeWidgetItem([name, f"r{rev}" if rev else "", author, date])
            if name == cur_name:
                for col in range(4):
                    f = it.font(col)
                    f.setBold(True)
                    it.setFont(col, f)
                    it.setForeground(col, Qt.GlobalColor.green)
                it.setText(0, f"{name}  （当前）")
            self.tree.addTopLevelItem(it)
        if not items:
            QTreeWidgetItem(self.tree, ["(branches/ 为空，可在上方创建第一个副分支)", "", "", ""])
        self.state_lbl.setText("")

    def _selected_branch(self):
        it = self.tree.currentItem()
        if not it:
            return ""
        return it.text(0).replace("  （当前）", "").strip()

    # ---------- 操作 ----------

    def on_create(self):
        repo = getattr(self, "repo", None)
        if not repo:
            return
        name = self.name_edit.text().strip()
        if not _valid_name(name):
            self.state_lbl.setText("名字不能为空，且不能含空格或 /")
            return
        dst = infer_branch_target(self._cur_url, name, self._repo_root)
        if not dst:
            self.state_lbl.setText("无法推断目标 URL")
            return
        if not self.main.confirm("新建副分支", f"从当前版本创建副分支？\n\n{self._cur_url}\n→ {dst}"):
            return
        msg = f"创建副分支 {name}（来自当前工作副本）"
        self.main.set_status(f"正在创建副分支 {name}…")

        def work():
            return repo.copy(self._cur_url, dst, message=msg)

        def done(_):
            self.name_edit.clear()
            self.main.set_status(f"副分支已创建: {dst}")
            self.reload()

        self.main.runner.run(work, on_result=done,
                             on_error=lambda e: self._fail("新建副分支", e))

    def on_switch(self):
        repo = getattr(self, "repo", None)
        name = self._selected_branch()
        if not repo or not name or name.startswith("("):
            return
        url = f"{self._base_url}/{name}"
        if url == self._cur_url.rstrip("/"):
            self.main.alert("切换", "已经在该分支上", error=False)
            return
        if not self.main.confirm("切换分支", f"把工作副本切换到 {url} ？\n\n未提交的本地修改会保留。"):
            return
        self.main.set_status(f"正在切换到 {name}…")

        def work():
            return repo.switch(url)

        def done(_):
            self.main._after_write_and_refresh(f"切换到 {name}")
            self.reload()

        self.main.runner.run(work, on_result=done,
                             on_error=lambda e: self._fail("切换", e))

    def on_merge(self):
        repo = getattr(self, "repo", None)
        name = self._selected_branch()
        if not repo or not name or name.startswith("("):
            return
        from .branch_page import MergePage
        url = f"{self._base_url}/{name}"
        dlg = MergePage(self.main, repo, self.theme,
                        on_done=lambda: self.main._after_write_and_refresh("合并"))
        dlg.src_edit.setText(url)
        dlg.exec()
        self.reload()

    def on_delete(self):
        repo = getattr(self, "repo", None)
        name = self._selected_branch()
        if not repo or not name or name.startswith("("):
            return
        url = f"{self._base_url}/{name}"
        cur_name = current_branch_name(self._cur_url)
        if name == cur_name:
            self.main.alert("删除分支", "当前工作副本正位于该分支上，请先切换走再删除。")
            return
        if not self.main.confirm("删除分支", f"确定从仓库中永久删除分支 {name} ？\n\n{url}\n\n此操作会提交到仓库（可通过历史找回）。"):
            return
        self.main.set_status(f"正在删除分支 {name}…")

        def work():
            return repo.delete_remote(url, message=f"删除副分支 {name}")

        def done(_):
            self.main.set_status(f"分支已删除: {name}")
            self.reload()

        self.main.runner.run(work, on_result=done,
                             on_error=lambda e: self._fail("删除分支", e))

    def _fail(self, label, e):
        self.main._after_fail(label, e)
        self.state_lbl.setText(f"{label}失败")
