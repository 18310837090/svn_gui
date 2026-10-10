#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分支/标签页 — 创建分支（svn copy）、切换（switch）、合并（merge）"""

import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QCheckBox, QComboBox, QFrame,
)

from ...core.repo import infer_branch_target, branches_base


def _vbox(dlg):
    root = QVBoxLayout(dlg)
    root.setContentsMargins(16, 14, 16, 14)
    root.setSpacing(8)
    return root


class BranchCreatePage(QDialog):
    """svn copy：从当前 URL（或指定源）复制到目标 URL 创建分支/标签，直接提交到仓库"""

    def __init__(self, parent, repo, theme):
        super().__init__(parent)
        self.theme = theme
        self.repo = repo
        self.setWindowTitle("创建分支/标签")
        self.resize(640, 320)

        c = theme.c
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        try:
            cur_url = repo.info().url
            cur_rev = repo.info().revision
        except Exception:
            cur_url, cur_rev = "", ""
        try:
            repo_root = repo.info().root
        except Exception:
            repo_root = ""
        self._cur_url = cur_url
        self._repo_root = repo_root

        root.addWidget(QLabel("源地址（默认当前工作副本 URL）"))
        self.src_edit = QLineEdit(cur_url)
        root.addWidget(self.src_edit)

        # 副分支快捷方式：只填名字，目标 URL 自动推断（仍可编辑）
        row = QHBoxLayout()
        row.addWidget(QLabel("分支名字（自动推断目标）"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("如 my-feature")
        row.addWidget(self.name_edit, 1)
        btn_guess = QPushButton("推断 →")
        btn_guess.setObjectName("flat")
        btn_guess.clicked.connect(self._infer)
        row.addWidget(btn_guess)
        root.addLayout(row)

        root.addWidget(QLabel("目标地址（新分支 URL，如 …/branches/my-feature）"))
        self.dst_edit = QLineEdit()
        root.addWidget(self.dst_edit)

        # 从当前 URL 推断 branches 路径提示
        if cur_url:
            guess = cur_url.replace("/trunk", "/branches/feature-1")
            if guess != cur_url:
                self.dst_edit.setPlaceholderText(f"例如: {guess}")

        # 名字变化时自动填目标
        self.name_edit.textChanged.connect(self._infer)

        root.addWidget(QLabel("提交说明"))
        self.msg_edit = QPlainTextEdit()
        self.msg_edit.setMaximumHeight(70)
        self.msg_edit.setPlaceholderText(f"创建分支（来自 r{cur_rev}）")
        root.addWidget(self.msg_edit)

        self.state = QLabel("")
        root.addWidget(self.state)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        ok = QPushButton("创建")
        ok.setObjectName("primary")
        ok.clicked.connect(self._run)
        btns.addWidget(ok)
        root.addLayout(btns)

    def _infer(self):
        """按名字把目标 URL 预填成 branches/<名字>"""
        name = self.name_edit.text().strip()
        if name and self._cur_url:
            guess = infer_branch_target(self._cur_url, name, self._repo_root)
            if guess:
                self.dst_edit.setText(guess)

    def _run(self):
        src = self.src_edit.text().strip()
        dst = self.dst_edit.text().strip()
        if not src or not dst:
            self.state.setText("请填写源和目标地址")
            self.state.setStyleSheet(f"color: {self.theme.c['yellow']};")
            return
        msg = self.msg_edit.toPlainText().strip() or f"创建分支 {dst}"
        repo = self.repo

        def work():
            return repo.copy(src, dst, message=msg)

        def done(_):
            self.parent().set_status(f"分支已创建: {dst}")
            self.accept()

        self.parent().runner.run(work, on_result=done,
                                 on_error=lambda e: self._fail(e))

    def _fail(self, e):
        self.state.setText(str(e))
        self.state.setStyleSheet(f"color: {self.theme.c['red']};")


class SwitchPage(QDialog):
    """svn switch：切换工作副本到另一个分支 URL"""

    def __init__(self, parent, repo, theme, on_done=None):
        super().__init__(parent)
        self.theme = theme
        self.repo = repo
        self.on_done = on_done
        self.setWindowTitle("切换 (switch)")
        self.resize(640, 220)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        try:
            cur_url = repo.info().url
        except Exception:
            cur_url = ""
        root.addWidget(QLabel(f"当前: {cur_url}"))
        root.addWidget(QLabel("目标分支 URL"))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://svn.example.com/svn/repo/branches/xxx")
        root.addWidget(self.url_edit)

        row = QHBoxLayout()
        row.addWidget(QLabel("版本号（可空）"))
        self.rev_edit = QLineEdit()
        self.rev_edit.setMaximumWidth(120)
        row.addWidget(self.rev_edit)
        row.addStretch(1)
        root.addLayout(row)

        self.state = QLabel("")
        root.addWidget(self.state)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        ok = QPushButton("切换")
        ok.setObjectName("primary")
        ok.clicked.connect(self._run)
        btns.addWidget(ok)
        root.addLayout(btns)

    def _run(self):
        url = self.url_edit.text().strip()
        if not url:
            return
        rev = self.rev_edit.text().strip() or None
        repo = self.repo

        def work():
            return repo.switch(url, rev)

        def done(_):
            if self.on_done:
                self.on_done("切换")
            self.accept()

        self.parent().runner.run(work, on_result=done,
                                 on_error=lambda e: (self.state.setText(str(e)),
                                                     self.state.setStyleSheet(f"color: {self.theme.c['red']};")))


class MergePage(QDialog):
    """svn merge：把 source 分支的 rev_range 合并进当前工作副本（先 dry-run 预览）"""

    def __init__(self, parent, repo, theme, on_done=None):
        super().__init__(parent)
        self.theme = theme
        self.repo = repo
        self.on_done = on_done
        self.setWindowTitle("合并 (merge)")
        self.resize(720, 460)

        c = theme.c
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        root.addWidget(QLabel("合并源分支 URL（把该分支的改动合并进当前工作副本）"))
        self.src_edit = QLineEdit()
        self.src_edit.setPlaceholderText("https://svn.example.com/svn/repo/branches/xxx")
        root.addWidget(self.src_edit)

        row = QHBoxLayout()
        row.addWidget(QLabel("版本范围（如 100:200，可空 = 全部未合并改动）"))
        self.range_edit = QLineEdit()
        self.range_edit.setMaximumWidth(200)
        row.addWidget(self.range_edit)
        self.dry_run = QCheckBox("先预览 (dry-run)")
        self.dry_run.setChecked(True)
        row.addWidget(self.dry_run)
        row.addStretch(1)
        root.addLayout(row)

        preview_lbl = QLabel("预览结果：")
        root.addWidget(preview_lbl)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setStyleSheet(
            f"QPlainTextEdit {{ background: {c['bg_panel']}; color: {c['fg']};"
            f" border-radius: 6px; font-family: 'Noto Sans Mono'; }}"
        )
        root.addWidget(self.preview, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        self.btn_apply = QPushButton("执行合并")
        self.btn_apply.setObjectName("primary")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._apply)
        btns.addWidget(self.btn_apply)
        btn_preview = QPushButton("预览")
        btn_preview.clicked.connect(self._preview)
        btns.addWidget(btn_preview)
        root.addLayout(btns)

        self._dry_output = None

    def _preview(self):
        src = self.src_edit.text().strip()
        if not src:
            return
        rng = self.range_edit.text().strip() or None
        repo = self.repo

        def work():
            return repo.merge(src, rev_range=rng, dry_run=True)

        def done(out):
            self.preview.setPlainText(out or "(无改动)")
            self.btn_apply.setEnabled(True)

        self.parent().runner.run(work, on_result=done,
                                 on_error=lambda e: self.preview.setPlainText(str(e)))

    def _apply(self):
        src = self.src_edit.text().strip()
        rng = self.range_edit.text().strip() or None
        repo = self.repo

        def work():
            return repo.merge(src, rev_range=rng, dry_run=False)

        def done(out):
            self.preview.setPlainText("合并完成:\n" + (out or ""))
            self.btn_apply.setEnabled(False)
            self.btn_apply.setText("完成")
            self.btn_apply.clicked.disconnect()
            self.btn_apply.clicked.connect(self.accept)
            if self.on_done:
                self.on_done("合并")

        self.parent().runner.run(work, on_result=done,
                                 on_error=lambda e: self.preview.setPlainText(str(e)))
