#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主窗口 — 左侧仓库/目录树、中部变更列表、右侧/底部标签页（日志、摘要）"""

import os

from PySide6.QtCore import Qt, QTimer, QObject, Signal, QFileSystemWatcher
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QBrush, QIcon, QPainter
from PySide6.QtCore import QRect
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QLineEdit, QSplitter, QTabWidget, QMenu, QFileDialog,
    QMessageBox, QInputDialog, QApplication, QStyle, QComboBox,
    QCheckBox, QPlainTextEdit, QFrame, QHeaderView,
)

from ..core.models import StatusItem
from ..core.repo import SvnRepo
from ..core.svn import SvnError
from ..core.store import Config, load_auth, save_auth, load_history
from ..core.worker import TaskRunner
from .theme import Theme
from .dialogs import AuthDialog, CheckoutDialog, PromptDialog
from .diffviewer import DiffViewer
from .pages.working_copy import WorkingCopyPage
from .pages.log_page import LogPage


ROLE_COLOR_KEY = {
    "green": "green", "yellow": "yellow", "red": "red",
    "purple": "purple", "gray": "gray",
}


class MainWindow(QMainWindow):
    # 渐变立体风图标（启动时生成一次，存于配置目录）
    _ICONS = {}

    @classmethod
    def _make_icons(cls):
        """绘制 Google Drive / macOS 风格的渐变立体图标：文件夹（开/合）+ 文件"""
        if cls._ICONS:
            return cls._ICONS
        from PySide6.QtGui import QPainter, QPixmap, QLinearGradient, QBrush, QPen, QPainterPath
        from PySide6.QtCore import QPointF, QRectF
        S = 64

        def folder(open_):
            pm = QPixmap(S, S)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            # 后板（暗渐变）
            g = QLinearGradient(0, 14, 0, 50)
            g.setColorAt(0, QColor("#7db4ec"))
            g.setColorAt(1, QColor("#5a93d6"))
            p.setBrush(QBrush(g))
            p.setPen(QPen(QColor(0, 0, 0, 40), 1))
            p.drawRoundedRect(QRectF(6, 14, 52, 36), 5, 5)
            tab = QPainterPath()
            tab.addRoundedRect(QRectF(6, 9, 20, 9), 4, 4)
            p.drawPath(tab)
            # 前板（亮渐变）
            g2 = QLinearGradient(0, 22, 0, 52)
            if open_:
                p.setBrush(QBrush(g2))
                front = QPainterPath()
                front.moveTo(4, 30)
                front.lineTo(60, 30)
                front.lineTo(54, 52)
                front.lineTo(10, 52)
                front.closeSubpath()
                p.drawPath(front)
            else:
                g2.setColorAt(0, QColor("#a3ccf9"))
                g2.setColorAt(1, QColor("#6ea6e8"))
                p.setBrush(QBrush(g2))
                p.drawRoundedRect(QRectF(4, 22, 56, 30), 5, 5)
                # 顶部高光
                hl = QLinearGradient(0, 22, 0, 30)
                hl.setColorAt(0, QColor(255, 255, 255, 110))
                hl.setColorAt(1, QColor(255, 255, 255, 0))
                p.setBrush(QBrush(hl))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(5, 23, 54, 7), 4, 4)
            p.end()
            return QIcon(pm)

        def file_icon():
            pm = QPixmap(S, S)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            g = QLinearGradient(0, 10, 0, 54)
            g.setColorAt(0, QColor("#ffffff"))
            g.setColorAt(1, QColor("#dfe6ee"))
            p.setBrush(QBrush(g))
            p.setPen(QPen(QColor(90, 110, 130, 160), 1.2))
            body = QPainterPath()
            body.moveTo(14, 10)
            body.lineTo(40, 10)
            body.lineTo(50, 20)
            body.lineTo(50, 54)
            body.lineTo(14, 54)
            body.closeSubpath()
            p.drawPath(body)
            g2 = QLinearGradient(40, 10, 50, 20)
            g2.setColorAt(0, QColor("#c8d4e0"))
            g2.setColorAt(1, QColor("#e8eef5"))
            p.setBrush(QBrush(g2))
            fold = QPainterPath()
            fold.moveTo(40, 10)
            fold.lineTo(50, 20)
            fold.lineTo(40, 20)
            fold.closeSubpath()
            p.drawPath(fold)
            p.setPen(QPen(QColor(120, 140, 160, 150), 2))
            for y in (28, 34, 40, 46):
                p.drawLine(QPointF(19, y), QPointF(45 if y != 46 else 36, y))
            p.end()
            return QIcon(pm)

        cls._ICONS = {"folder": folder(False), "folder_open": folder(True),
                      "file": file_icon()}
        return cls._ICONS

    def _dir_icon(self, open_=False):
        return self._make_icons()["folder_open" if open_ else "folder"]

    def _file_icon(self):
        return self._make_icons()["file"]

    def __init__(self, start_dir=None):
        super().__init__()
        self.setWindowTitle("SVN")
        self.resize(1200, 780)
        self.setMinimumSize(960, 620)

        self.cfg = Config()
        self.theme = Theme(self.cfg["theme"])
        self.runner = TaskRunner(self)
        self._auth_signal = self._AuthSignal()
        self._auth_signal.request.connect(self._show_auth)

        self.repo = None
        self.items = []            # [StatusItem]
        self._active_dir = None    # 目录过滤 (None = 全部)
        self._fs_watcher = QFileSystemWatcher(self)
        self._fs_watcher.directoryChanged.connect(self._on_fs_changed)
        self._fs_timer = QTimer(self)
        self._fs_timer.setSingleShot(True)
        self._fs_timer.setInterval(600)   # 防抖: 批量文件操作只触发一次刷新
        self._fs_timer.timeout.connect(self.refresh)
        self._watched_paths = set()

        self._apply_theme()
        self._build_ui()
        self._build_shortcuts()
        self._build_menus()

        d = start_dir or self.cfg["last_dir"]
        if d and os.path.isdir(d):
            QTimer.singleShot(50, lambda: self.open_dir(d))

    def closeEvent(self, event):
        # 等待后台 svn 线程收尾，避免 "QThread: Destroyed while thread is still running"
        self.runner.shutdown()
        super().closeEvent(event)

    # ---------- 主题 ----------

    def _apply_theme(self):
        from PySide6.QtGui import QPalette
        c = self.theme.c
        self.setStyleSheet(self.theme.qss())
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor(c["bg"]))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(c["fg"]))
        pal.setColor(QPalette.ColorRole.Base, QColor(c["bg_panel"]))
        pal.setColor(QPalette.ColorRole.Text, QColor(c["fg"]))
        pal.setColor(QPalette.ColorRole.Button, QColor(c["bg_input"]))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor(c["fg"]))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(c["select_bg"]))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(c["fg"]))
        self.setPalette(pal)

    def switch_theme(self, name):
        self.theme.set(name)
        self.cfg["theme"] = name
        self._apply_theme()

    # ---------- UI 构建 ----------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(0)

        # 左: 目录树
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self._label("目录"))
        self.dir_tree = QTreeWidget()
        self.dir_tree.setHeaderHidden(True)
        self.dir_tree.setColumnCount(2)
        self.dir_tree.setRootIsDecorated(True)
        self.dir_tree.itemClicked.connect(self._on_tree_click)
        self.dir_tree.itemDoubleClicked.connect(self._on_tree_dclick)
        self.dir_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.dir_tree.customContextMenuRequested.connect(self._on_tree_menu)
        self.dir_tree.setUniformRowHeights(True)
        self.dir_tree.header().setStretchLastSection(False)
        self.dir_tree.header().setMinimumSectionSize(24)
        self.dir_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.dir_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        lv.addWidget(self.dir_tree, 1)

        # 中: 代码区（显示当前查看的文件内容）
        from PySide6.QtGui import QFont
        from .code_view import CodeView
        mid = QWidget()
        mv = QVBoxLayout(mid)
        mv.setContentsMargins(0, 0, 0, 0)
        mhead = QHBoxLayout()
        mhead.setContentsMargins(8, 0, 8, 0)
        self.code_title = self._label("代码区域")
        mhead.addWidget(self.code_title)
        mhead.addStretch(1)
        mv.addLayout(mhead)

        self.code_view = CodeView(self.theme)
        self.code_view.setPlaceholderText("选择文件查看内容…")
        mv.addWidget(self.code_view, 1)

        # 右: 标签页（概览 / 变更文件 / 提交日志）+ 操作日志
        self.tabs = QTabWidget()
        self.summary_page = WorkingCopyPage(self)
        self.log_page = LogPage(self)
        from .pages.side_branch_page import SideBranchPage
        self.side_branch_page = SideBranchPage(self)
        self.tabs.addTab(self.summary_page, "概览")
        self.tabs.addTab(self._build_changes_page(), "变更文件")
        self.tabs.addTab(self.log_page, "提交日志")
        self.tabs.addTab(self.side_branch_page, "副分支")
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(self.tabs, 1)
        rv.addWidget(self._build_op_log(), 0)

        # 三栏之间用 QSplitter，可左右拖动调整间距
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(left)
        self.splitter.addWidget(mid)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 6)
        self.splitter.setStretchFactor(2, 4)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(8)
        root.addWidget(self.splitter, 1)

        # 状态栏
        self.statusBar().showMessage("就绪")

    def _build_changes_page(self):
        """「变更文件」标签页: 状态统计 + 文件列表 + 过滤"""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 4, 8, 4)
        v.setSpacing(6)

        # 顶栏: 按状态统计的筛选 chips + 过滤框
        top = QHBoxLayout()
        top.setSpacing(6)
        self._chip_buttons = {}
        from PySide6.QtWidgets import QToolButton
        for code, desc in [("M", "修改"), ("A", "新增"), ("D", "删除"),
                           ("R", "替换"), ("C", "冲突"), ("?", "未版本控制")]:
            b = QToolButton()
            b.setText(f"{desc} 0")
            b.setCheckable(True)
            b.setToolTip(f"只看 {desc}（{code}）")
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            b.setStyleSheet(
                f"QToolButton {{ border: 1px solid {self.theme.c['border']};"
                f" border-radius: 10px; padding: 2px 10px; color: {self.theme.c['fg_dim']}; }}"
                f"QToolButton:checked {{ background: {self.theme.c['select_bg']};"
                f" color: {self.theme.c['fg']}; border-color: {self.theme.c['accent']}; }}"
            )
            # 允许压缩，避免整行最小宽度过大、把右栏拖不动
            from PySide6.QtWidgets import QSizePolicy
            b.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            b.toggled.connect(self._rebuild_file_list)
            self._chip_buttons[code] = b
            top.addWidget(b)
        top.addStretch(1)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("过滤文件名…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setMaximumWidth(200)
        self.filter_edit.textChanged.connect(self._rebuild_file_list)
        top.addWidget(self.filter_edit)
        # 主界面提交按钮: 打开提交对话框（相当于 Ctrl+Return）
        from PySide6.QtWidgets import QPushButton as _Btn
        self.btn_commit_main = _Btn("下一步 (0)")
        self.btn_commit_main.setObjectName("primary")
        self.btn_commit_main.setToolTip("打开提交对话框 (Ctrl+Return)")
        self.btn_commit_main.setEnabled(False)
        self.btn_commit_main.clicked.connect(self.on_commit)
        top.addWidget(self.btn_commit_main)
        v.addLayout(top)

        # 文件列表
        self.file_list = QListWidget()
        self.file_list.setSpacing(2)
        self.file_list.itemDoubleClicked.connect(self._on_file_dclick)
        self.file_list.itemSelectionChanged.connect(self._on_file_selected)
        self.file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._on_file_menu)
        v.addWidget(self.file_list, 1)
        return page

    def _on_file_selected(self, *_):
        """变更列表选中文件 → 代码区显示其内容"""
        sel = self._selected_items()
        if sel:
            self._show_in_code_view(sel[0])

    def _build_op_log(self):
        """底部操作日志面板: 只读文本框，显示每步 svn 操作的输出"""
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(2)
        head = QHBoxLayout()
        self.oplog_title = QLabel("操作日志")
        self.oplog_title.setStyleSheet("font-weight: bold;")
        head.addWidget(self.oplog_title)
        head.addStretch(1)
        clear_btn = QPushButton("清空")
        clear_btn.setObjectName("flat")
        clear_btn.clicked.connect(lambda: self.oplog.clear())
        head.addWidget(clear_btn)
        v.addLayout(head)
        self.oplog = QPlainTextEdit()
        self.oplog.setReadOnly(True)
        self.oplog.setMaximumHeight(140)
        self.oplog.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        v.addWidget(self.oplog)
        return box

    def log(self, text, level="info"):
        """追加一条操作日志。level: info / ok / warn / err"""
        from datetime import datetime
        c = self.theme.c
        color = {"ok": c["green"], "warn": c["yellow"], "err": c["red"]}.get(level, c["fg_dim"])
        ts = datetime.now().strftime("%H:%M:%S")
        self.oplog.appendHtml(
            f'<span style="color:{c["fg_dim"]}">[{ts}]</span> '
            f'<span style="color:{color}">{self._escape(text)}</span>'
        )
        sb = self.oplog.verticalScrollBar()
        sb.setValue(sb.maximum())

    @staticmethod
    def _escape(text):
        return (str(text).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))

    def _label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        return lbl

    def _dimlabel(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("status")
        return lbl

    # ---------- 快捷键 ----------

    # 动作注册表: id -> (菜单文字, 默认快捷键, 回调方法名)
    ACTIONS = {
        "open":        ("打开工作副本…", "Ctrl+O", "on_open_dir"),
        "update":      ("更新 (update)", "F5", "on_update"),
        "commit":      ("提交…", "Ctrl+Return", "on_commit"),
        "quit":        ("退出", "Ctrl+Q", "close"),
        "add":         ("添加未版本控制文件…", "", "on_add"),
        "ignore":      ("加入忽略清单 (svn:ignore)…", "", "on_ignore"),
        "cleanup":     ("清理 (cleanup)", "", "on_cleanup"),
        "resolve":     ("解决冲突…", "", "on_resolve"),
        "lock":        ("锁定选中文件…", "", "on_lock"),
        "unlock":      ("解锁选中文件", "", "on_unlock"),
        "branch":      ("创建分支/标签…", "", "on_branch_create"),
        "side_branch": ("副分支管理…", "", "on_side_branches"),
        "switch":      ("切换 (switch)…", "", "on_switch"),
        "merge":       ("合并 (merge)…", "", "on_merge"),
    }

    def _action_shortcut(self, action_id):
        """某动作的当前快捷键：config 覆盖默认值；空串 = 用户禁用"""
        custom = self.cfg.data.get("shortcuts", {})
        if action_id in custom:
            return custom[action_id]
        return self.ACTIONS[action_id][1]

    def _bind_action(self, action_id):
        """创建 QAction 并按当前配置绑定快捷键与回调"""
        text, _, slot = self.ACTIONS[action_id]
        act = QAction(text, self)
        sc = self._action_shortcut(action_id)
        if sc:
            act.setShortcut(QKeySequence(sc))
        act.triggered.connect(getattr(self, slot))
        self._actions[action_id] = act
        return act

    def _build_shortcuts(self):
        # 菜单在 _build_shortcuts 之后构建，这里只初始化容器
        self._actions = {}

    def apply_shortcuts(self):
        """把 config 里的快捷键套用到所有已注册的 QAction"""
        for action_id, act in self._actions.items():
            sc = self._action_shortcut(action_id)
            act.setShortcut(QKeySequence(sc) if sc else QKeySequence())

    def _build_menus(self):
        mbar = self.menuBar()

        m_file = mbar.addMenu("文件(&F)")
        m_file.addAction(self._bind_action("open"))
        act_checkout = QAction("检出（拉取）…", self)
        act_checkout.triggered.connect(self.on_checkout)
        m_file.addAction(act_checkout)
        # 设置（下一级: 快捷键、主题），放在导出上面
        m_prefs = m_file.addMenu("设置")
        act_shortcut = QAction("快捷键", self)
        act_shortcut.triggered.connect(self.on_shortcut_settings)
        m_prefs.addAction(act_shortcut)
        m_prefs_theme = m_prefs.addMenu("主题")
        act_dark = QAction("深色", self, checkable=True, checked=self.theme.name == "dark")
        act_light = QAction("浅色", self, checkable=True, checked=self.theme.name == "light")
        act_dark.triggered.connect(lambda: self._set_theme_action("dark", act_dark, act_light))
        act_light.triggered.connect(lambda: self._set_theme_action("light", act_dark, act_light))
        m_prefs_theme.addAction(act_dark)
        m_prefs_theme.addAction(act_light)
        self._prefs_theme_acts = (act_dark, act_light)
        act_export = QAction("导出…", self)
        act_export.triggered.connect(self.on_export)
        m_file.addAction(act_export)
        m_file.addSeparator()
        m_repos = m_file.addMenu("最近仓库")
        self.m_repos = m_repos
        self._rebuild_repo_menu(m_repos)
        m_file.addAction(self._bind_action("quit"))

        m_svn = mbar.addMenu("SVN(&S)")
        m_svn.addAction(self._bind_action("update"))
        m_svn.addAction(self._bind_action("commit"))
        m_svn.addSeparator()
        m_svn.addAction(self._bind_action("add"))
        m_svn.addAction(self._bind_action("ignore"))
        m_svn.addSeparator()
        m_svn.addAction(self._bind_action("cleanup"))
        m_svn.addAction(self._bind_action("resolve"))
        m_svn.addSeparator()
        m_svn.addAction(self._bind_action("lock"))
        m_svn.addAction(self._bind_action("unlock"))

        m_branch = mbar.addMenu("分支(&B)")
        m_branch.addAction(self._bind_action("side_branch"))
        m_branch.addSeparator()
        m_branch.addAction(self._bind_action("branch"))
        m_branch.addAction(self._bind_action("switch"))
        m_branch.addAction(self._bind_action("merge"))

        # 主题选择已移到 文件 → 设置 → 主题（原"查看"菜单已移除）

        m_help = mbar.addMenu("帮助(&H)")
        act_help = QAction("快捷键", self)
        act_help.triggered.connect(self.on_help)
        m_help.addAction(act_help)

    def _set_theme_action(self, name, *acts):
        for a in acts:
            a.setChecked(a.text().lower().startswith(name[:4]) or
                         (name == "dark" and a.text() == "深色") or
                         (name == "light" and a.text() == "浅色"))
        self.switch_theme(name)

    def switch_theme(self, name):
        if name == self.theme.name:
            return
        self.switch_theme_impl(name)

    def switch_theme_impl(self, name):
        self.theme.set(name)
        self.cfg["theme"] = name
        self._apply_theme()
        # 重建各页面内容（刷新颜色）
        self.summary_page.apply_theme()
        if hasattr(self, "code_view"):
            self.code_view.apply_theme(self.theme)
        if self.repo:
            self.refresh()

    def _rebuild_repo_menu(self, menu):
        menu.clear()
        for r in self.cfg.repos:
            act = QAction(r["name"], menu)
            act.triggered.connect(lambda checked=False, p=r["path"]: self.open_dir(p))
            menu.addAction(act)
        menu.addSeparator()
        act_add = QAction("添加仓库…", menu)
        act_add.triggered.connect(self.on_add_repo)
        menu.addAction(act_add)
        if self.cfg.repos:
            m_rm = menu.addMenu("移除仓库")
            self._fill_remove_menu(m_rm)

    def _fill_remove_menu(self, m_rm):
        """填充「移除仓库」子菜单：每行 名称 + ✕ 按钮。
        点击 ✕ 只移除该行，菜单保持打开。"""
        from PySide6.QtWidgets import QWidgetAction, QToolButton
        m_rm.clear()
        for r in self.cfg.repos:
            row = QWidget(m_rm)
            row.setStyleSheet("background: transparent;")
            lay = QHBoxLayout(row)
            lay.setContentsMargins(8, 3, 10, 3)
            lay.setSpacing(6)
            lbl = QLabel(r["name"], row)
            lbl.setStyleSheet("background: transparent;")
            lay.addWidget(lbl)
            btn = QToolButton(row)
            lay.addWidget(btn)  # ✕ 紧跟名字之后，不拉伸
            btn.setText("✕")
            btn.setToolTip(f"移除 {r['name']}")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QToolButton{border:none;color:#e05555;font-weight:bold;"
                "padding:0 4px;border-radius:4px;background:transparent;}"
                "QToolButton:hover{color:#fff;background:#e05555;}"
            )
            wa = QWidgetAction(m_rm)
            wa.setDefaultWidget(row)
            wa.setText(" ")  # 空文本：禁用 QWidgetAction 自身的 hover 高亮（会盖住整行）
            path = r["path"]

            def on_remove(_checked=False, p=path, w=wa):
                self.cfg.remove_repo(p)
                m_rm.removeAction(w)  # 只移除该行，不关闭菜单

            btn.clicked.connect(on_remove)
            m_rm.addAction(wa)

    # ---------- 状态栏辅助 ----------

    def set_status(self, text):
        self.statusBar().showMessage(text)
        self.log(text)

    def alert(self, title, msg, error=True):
        if error:
            QMessageBox.critical(self, title, msg)
        else:
            QMessageBox.information(self, title, msg)

    def confirm(self, title, msg):
        return QMessageBox.question(self, title, msg) == QMessageBox.StandardButton.Yes

    # ---------- 认证 ----------

    class _AuthSignal(QObject):
        """后台线程 → 主线程的认证请求信号（QTimer.singleShot 跨线程不会触发，
        必须用信号槽的队列连接切换线程）"""
        request = Signal(object, object)   # (err_text, reply: {"q": Queue})

    def _make_auth_prompt(self):
        """返回给 core 的认证回调。core 在后台线程执行，
        经信号队列连接切回主线程弹窗，后台线程阻塞等待结果。"""

        repo_ref = self.repo
        sig = self._auth_signal

        def prompt(err_text):
            saved = {}
            try:
                url = repo_ref.info().url if repo_ref else ""
            except Exception:
                url = ""
            try:
                auth = load_auth()
                saved = auth.get(url) or auth.get("_last_user") or {}
            except Exception:
                pass
            # 已保存过凭证 → 直接静默重试，不弹窗
            if saved.get("username") and saved.get("password"):
                return {"username": saved["username"], "password": saved["password"],
                        "save": False}
            import queue as _q
            q = _q.Queue()
            # 队列连接: emit 从后台线程发出，槽在主线程执行
            sig.request.emit((err_text, saved), q)
            try:
                return q.get(timeout=300)
            except Exception:
                return None

        return prompt

    def _show_auth(self, payload, q):
        err_text, saved = payload
        dlg = AuthDialog(self, err_text,
                         preset_user=(saved or {}).get("username", ""),
                         preset_pwd=(saved or {}).get("password", ""),
                         theme=self.theme)
        dlg.exec()
        cred = dlg.result
        if cred and cred.get("save") and self.repo:
            try:
                url = self.repo.info().url
                auth = load_auth()
                auth[url] = {"username": cred["username"], "password": cred["password"]}
                auth["_last_user"] = {"username": cred["username"], "password": cred["password"]}
                save_auth(auth)
            except Exception:
                pass
        q.put(cred)

    # ---------- 打开仓库 ----------

    def _current_url(self):
        """当前仓库 URL；工作副本无效/不存在时返回空（预填失败不该报错）"""
        try:
            return self.repo.info().url if self.repo else ""
        except Exception:
            return ""

    def on_checkout(self):
        """检出（拉取）: URL + 账号密码 → 选空目录 → 后台 svn checkout → 打开"""
        # 预填上次用的账号
        preset_user = preset_pwd = ""
        try:
            auth = load_auth()
            saved = auth.get("_last_user") or {}
            preset_user = saved.get("username", "")
            preset_pwd = saved.get("password", "")
        except Exception:
            pass
        dlg = CheckoutDialog(self, preset_url=self._current_url(),
                             preset_user=preset_user, preset_pwd=preset_pwd,
                             theme=self.theme)
        if not dlg.exec() or not dlg.result or not dlg.result["url"]:
            return
        info = dlg.result
        url = info["url"]
        d = QFileDialog.getExistingDirectory(self, "选择检出目标目录（需为空目录）", self.cfg["last_dir"])
        if not d:
            return
        d = os.path.abspath(d)
        if os.path.isdir(d) and os.listdir(d):
            self.alert("错误", f"{d}\n目录不为空，请选择空目录")
            return
        repo = SvnRepo(d, auth_prompt=self._make_auth_prompt())
        self.set_status(f"正在检出 {url} …")

        def work():
            out = repo.checkout(url, d, username=info["username"] or None,
                                password=info["password"] or None)
            return out

        def done(out):
            # 输出每个检出文件（A 路径），最多 200 行，多出折叠为计数
            lines = [ln for ln in out.splitlines() if ln.startswith("A ")]
            shown = lines[:200]
            for ln in shown:
                path = ln[2:].strip()
                # 去掉目标目录前缀，显示相对路径
                rel = os.path.relpath(path, d) if path.startswith(d) else path
                self.log(f"A  {rel}")
            if len(lines) > len(shown):
                self.log(f"… 其余 {len(lines) - len(shown)} 个文件省略", level="info")
            n = len(lines)
            self.set_status(f"检出完成: {n} 个文件 → {d}")
            if info["save"] and info["username"]:
                try:
                    a = load_auth()
                    a["_last_user"] = {"username": info["username"],
                                       "password": info["password"]}
                    save_auth(a)
                except Exception:
                    pass
            self.open_dir(d)

        self.runner.run(work, on_result=done, on_error=lambda e: self._after_fail("检出", e))

    def on_add_repo(self):
        d = QFileDialog.getExistingDirectory(self, "添加仓库", self.cfg["last_dir"])
        if not d:
            return
        d = os.path.abspath(d)
        probe = SvnRepo(d)
        if not probe.is_working_copy():
            self.alert("错误", f"{d}\n不是 SVN 工作副本")
            return
        self.cfg.add_repo(d)
        self.open_dir(d)

    def on_open_dir(self):
        d = QFileDialog.getExistingDirectory(self, "打开工作副本", self.cfg["last_dir"])
        if d:
            self.open_dir(os.path.abspath(d))

    def open_dir(self, d):
        d = os.path.abspath(d)
        if not os.path.isdir(d):
            self.alert("错误", f"目录不存在: {d}")
            return
        self.repo = SvnRepo(d, auth_prompt=self._make_auth_prompt())
        self.cfg["last_dir"] = d
        probe = SvnRepo(d)
        if probe.is_working_copy():
            self.cfg.add_repo(d)
            self.set_status(f"已打开: {d}")
            self._watch_dirs()
            self.refresh()
        else:
            self.set_status(f"已打开（不是 SVN 工作副本）: {d}")
            self.items = []
            self._rebuild_tree()
            self._rebuild_file_list()
            self.summary_page.clear()
            self.log_page.clear()
            self.side_branch_page.clear()

    # ---------- 刷新 ----------

    def _watch_dirs(self):
        """监视工作副本根目录（及前两层子目录），文件变动时自动刷新目录树。
        只监视目录（svn status 才能感知文件级变更），不监视 .svn 内部。"""
        w = self._fs_watcher
        old = set(w.directories())
        if old:
            w.removePaths(list(old))
        self._watched_paths = set()
        if not self.repo or not os.path.isdir(self.repo.path):
            return
        root = self.repo.path
        w.addPath(root)
        self._watched_paths.add(root)
        for d in self._list_dirs(root):
            p = os.path.join(root, d)
            if p not in self._watched_paths:
                w.addPath(p)
                self._watched_paths.add(p)
            for sub in self._list_dirs(p):
                sp = os.path.join(p, sub)
                w.addPath(sp)
                self._watched_paths.add(sp)

    @staticmethod
    def _list_dirs(path):
        try:
            return [e for e in os.listdir(path)
                    if os.path.isdir(os.path.join(path, e)) and e != ".svn"]
        except OSError:
            return []

    def _on_fs_changed(self, path):
        # 防抖: 600ms 内的连续变动合并为一次刷新
        self._fs_timer.start()

    def refresh(self):
        if not self.repo:
            return
        self.set_status("正在获取状态…")
        repo = self.repo
        self.runner.run(
            repo.status,
            on_result=self._on_status,
            on_error=lambda e: self.alert("刷新失败", str(e)),
        )

    def _on_status(self, items):
        self.items = items
        self._rebuild_tree()
        self._rebuild_file_list()
        self.summary_page.update_info(self.repo, items)
        self.log_page.load(self.repo)
        self.set_status(f"共 {len(items)} 个变更文件")
        # 目录树重建后重新挂监视（新目录可能出现了）
        self._watch_dirs()

    # ---------- 目录树 ----------

    def _rebuild_tree(self):
        """目录树: 根节点为工作副本目录名，下挂实际目录结构，变更文件标状态码。"""
        from PySide6.QtWidgets import QTreeWidgetItem
        tree = self.dir_tree
        tree.clear()

        c = self.theme.c
        root_name = os.path.basename(self.repo.path) if self.repo else "全部"
        root = QTreeWidgetItem([root_name, ""])
        root.setIcon(0, self._dir_icon(open_=True))
        tree.addTopLevelItem(root)

        # 变更索引: 相对路径 → StatusItem
        changes = {it.path: it for it in self.items}

        if self.repo and os.path.isdir(self.repo.path):
            self._fill_wc_tree(root, self.repo.path, depth=0, changes=changes)
        else:
            # 非工作副本: 退回按变更列表聚合
            dirs = {}
            for it in self.items:
                dirs.setdefault(it.dirname, []).append(it)
            for d in sorted(dirs):
                for it in sorted(dirs[d], key=lambda x: x.name):
                    node = QTreeWidgetItem([f"{d}/{it.name}" if d else it.name, it.code])
                    color = QColor(c[ROLE_COLOR_KEY.get(it.role, "fg")])
                    node.setForeground(0, QBrush(color))
                    node.setData(0, Qt.ItemDataRole.UserRole, it)
                    root.addChild(node)

        root.setExpanded(True)

    def _fill_wc_tree(self, parent_item, path, depth, changes, parent_change=None):
        """递归填充工作副本目录树（跳过 .svn，最多 4 层，全部条目显示）。
        带变更的条目用状态码着色，纯目录显示子项数量。
        父目录自身有状态（如未版本控制）时，子项继承同样的状态标识。"""
        from PySide6.QtWidgets import QTreeWidgetItem
        c = self.theme.c
        try:
            entries = sorted(os.listdir(path), key=str.lower)
        except OSError:
            return
        dirs = [e for e in entries
                if os.path.isdir(os.path.join(path, e)) and e != ".svn"]
        files = [e for e in entries
                 if not os.path.isdir(os.path.join(path, e)) and e != ".svn"]
        for name in dirs + files:
            full = os.path.join(path, name)
            rel = os.path.relpath(full, self.repo.path)
            is_dir = name in dirs
            change = changes.get(rel) or parent_change
            if is_dir:
                # 目录: 渐变文件夹图标 + 名字，最右列显示该目录下的变更条数
                # 目录自身有状态（如未版本控制）→ 直接数磁盘上的子项数
                if change is not None:
                    try:
                        sub = os.listdir(full)
                    except OSError:
                        sub = []
                    n = len([e for e in sub if e != ".svn"])
                else:
                    n = sum(1 for p in changes if p.startswith(rel + "/"))
                if n:
                    node = QTreeWidgetItem([name, str(n)])
                    color = QColor(c["accent"] if not change else c[ROLE_COLOR_KEY.get(change.role, "fg")])
                    node.setForeground(0, QBrush(color))
                    node.setForeground(1, QBrush(color))
                    if change:
                        node.setData(0, Qt.ItemDataRole.UserRole, change)
                else:
                    node = QTreeWidgetItem([name, ""])
                node.setIcon(0, self._dir_icon())
                node.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                parent_item.addChild(node)
                if depth < 3:
                    self._fill_wc_tree(node, full, depth + 1, changes,
                                       parent_change=change)
            else:
                # 文件: 有变更标 1，与目录计数方式一致
                node = QTreeWidgetItem([name, "1" if change else ""])
                color = QColor(c[ROLE_COLOR_KEY.get(change.role, "fg_dim")] if change else c["fg_dim"])
                node.setForeground(0, QBrush(color))
                node.setIcon(0, self._file_icon())
                if change:
                    node.setForeground(1, QBrush(color))
                # 无论有无变更都挂上条目，点击/双击才能在代码区加载内容
                node.setData(0, Qt.ItemDataRole.UserRole,
                             change or StatusItem(path=rel, code=""))
                parent_item.addChild(node)

    def _on_tree_click(self, item, column):
        # 有变更数据的节点 → 定位该文件
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is not None:
            self.file_list.clearSelection()
            # 在文件列表里找到对应项并选中
            for i in range(self.file_list.count()):
                if self.file_list.item(i).data(Qt.ItemDataRole.UserRole) is data:
                    self.file_list.item(i).setSelected(True)
                    self.file_list.scrollToItem(self.file_list.item(i))
                    break
            # 代码区显示该文件内容
            if not os.path.isdir(
                    os.path.join(self.repo.path, data.path) if self.repo else data.path):
                self._show_in_code_view(data)
            return
        if item.parent() is None:
            # 点根节点（工作副本根目录）→ 清过滤
            self._active_dir = None
            self._rebuild_file_list()
            return
        # 目录节点: 按目录过滤变更列表
        text = item.text(0)
        name = text.rsplit(" (", 1)[0] if " (" in text else text  # 去掉 "(n)" 变更计数
        self._active_dir = None if name in ("/", "全部") else name
        self._rebuild_file_list()

    def _on_tree_dclick(self, item, column):
        # 双击文件节点 → 代码区加载内容（不弹独立窗口）
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is not None and not os.path.isdir(
                os.path.join(self.repo.path, data.path) if self.repo else data.path):
            self._show_in_code_view(data)

    def _tree_node_fs_path(self, item):
        """目录树节点对应的本地文件系统路径"""
        if not self.repo:
            return None
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is not None:
            return os.path.join(self.repo.path, data.path)
        # 无数据的节点（根/普通目录）: 沿父节点拼路径
        parts = []
        cur = item
        while cur is not None and cur.parent() is not None:
            text = cur.text(0)
            parts.append(text.rsplit(" (", 1)[0] if " (" in text else text)
            cur = cur.parent()
        if not parts:
            return self.repo.path
        return os.path.join(self.repo.path, *reversed(parts))

    def _on_tree_menu(self, pos):
        item = self.dir_tree.itemAt(pos)
        if not item:
            return
        fs_path = self._tree_node_fs_path(item)
        if not fs_path:
            return
        menu = QMenu(self)
        if os.path.isdir(fs_path):
            menu.addAction("打开文件夹", lambda: self._toggle_tree_node(item))
        else:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data is not None:
                menu.addAction("打开文件", lambda: self._show_in_code_view(data))
        menu.addAction("打开原始路径", lambda: self._open_fs_path(fs_path))
        menu.exec(self.dir_tree.viewport().mapToGlobal(pos))

    def _toggle_tree_node(self, item):
        """目录树节点折叠/展开切换"""
        item.setExpanded(not item.isExpanded())

    def _open_fs_path(self, path):
        """用系统文件管理器打开路径（目录直接开，文件开所在目录并选中）"""
        import subprocess
        if os.path.isdir(path):
            subprocess.Popen(["xdg-open", path])
        elif os.path.isfile(path):
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
        else:
            self.set_status(f"路径不存在: {path}")

    # ---------- 文件列表 ----------

    def _show_in_code_view(self, it):
        """中间代码区显示文件内容，标题为文件路径"""
        if it is None:
            return
        self.code_title.setText(it.path or "代码")
        if not self.repo or it.code in ("D", "!", "missing"):
            self.code_view.set_content(f"（{it.desc}，无本地内容可显示）")
            return
        path = os.path.join(self.repo.path, it.path)
        if not os.path.isfile(path):
            self.code_view.set_content(f"文件不存在: {path}")
            return
        try:
            with open(path, "rb") as f:
                raw = f.read(8 * 1024 * 1024)
        except OSError as e:
            self.code_view.set_content(f"无法读取: {e}")
            return
        if b"\x00" in raw[:4096]:
            self.code_view.set_content("（二进制文件，不支持预览）")
            return
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content = raw.decode("gbk")
            except UnicodeDecodeError:
                content = raw.decode("utf-8", errors="replace")
        self.code_view.set_content(content, path=path)

    def _visible_items(self):
        """当前过滤/目录/状态筛选下可见的变更项（提交按钮按此计数）"""
        checked = {code for code, b in getattr(self, "_chip_buttons", {}).items() if b.isChecked()}
        pattern = self.filter_edit.text().strip().lower() if hasattr(self, "filter_edit") else ""
        out = []
        for it in self.items:
            if self._active_dir and not it.dirname.startswith(self._active_dir):
                continue
            if checked and it.code not in checked:
                continue
            if pattern and pattern not in it.path.lower():
                continue
            out.append(it)
        return out

    def _rebuild_file_list(self):
        self.file_list.clear()
        c = self.theme.c
        pattern = self.filter_edit.text().strip().lower() if hasattr(self, "filter_edit") else ""
        # 状态 chips: 勾选的只看对应状态（都没勾 = 全部）
        checked = {code for code, b in getattr(self, "_chip_buttons", {}).items() if b.isChecked()}
        # 更新 chips 上的计数
        if hasattr(self, "_chip_buttons"):
            code_count = {}
            for it in self.items:
                code_count[it.code] = code_count.get(it.code, 0) + 1
            for code, b in self._chip_buttons.items():
                n = code_count.get(code, 0)
                desc = b.text().rsplit(" ", 1)[0] if " " in b.text() else b.text()
                b.setText(f"{desc} {n}")
                b.setVisible(n > 0 or b.isChecked())
        count = 0
        for it in self.items:
            if self._active_dir and not it.dirname.startswith(self._active_dir):
                continue
            if checked and it.code not in checked:
                continue
            if pattern and pattern not in it.path.lower():
                continue
            count += 1
            color = QColor(c[ROLE_COLOR_KEY.get(it.role, "fg")])
            lbl = QLabel(f' {it.code}  {it.path}   — {it.desc}')
            lbl.setStyleSheet(f"color: {color.name()}; padding: 2px;")
            item = QListWidgetItem()
            item.setSizeHint(lbl.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, it)
            self.file_list.addItem(item)
            self.file_list.setItemWidget(item, lbl)
        self._update_commit_btn()

    def _update_commit_btn(self):
        """主界面提交按钮: 显示当前可见变更数，无可提交项时禁用"""
        if not hasattr(self, "btn_commit_main"):
            return
        n = len(self._visible_items())
        self.btn_commit_main.setText(f"下一步 ({n})")
        self.btn_commit_main.setEnabled(n > 0 and self.repo is not None)

    def _selected_items(self):
        return [self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.file_list.count())
                if self.file_list.item(i).isSelected()]

    def _on_file_dclick(self, item):
        it = item.data(Qt.ItemDataRole.UserRole)
        if it:
            self.open_file(it)

    def open_file(self, it):
        """在软件内查看文件内容（丢失/删除的文件不给打开）"""
        if not self.repo or it.code in ("D", "!", "missing"):
            return
        path = os.path.join(self.repo.path, it.path)
        if not os.path.isfile(path):
            self.set_status(f"文件不存在: {path}")
            return
        from .fileviewer import FileViewer
        FileViewer(self, path, self.theme).show()

    def _on_file_menu(self, pos):
        item = self.file_list.itemAt(pos)
        if not item:
            return
        it = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        if it.code not in ("D", "!"):
            menu.addAction("打开文件", lambda: self.open_file(it))
        menu.addAction("查看 Diff", lambda: self.show_diff([it]))
        menu.addAction("查看历史 (blame)", lambda: self.show_blame(it))
        menu.addSeparator()
        if it.code == "?":
            menu.addAction("svn add", lambda: self._do_add([it]))
            menu.addAction("加入忽略清单…", lambda: self.on_ignore([it.name]))
        if it.code in ("A", "M", "R", "!"):
            menu.addAction("还原 (revert)", lambda: self._do_revert([it]))
        if it.code == "C":
            menu.addAction("解决冲突…", lambda: self.on_resolve([it]))
        menu.addSeparator()
        menu.addAction("打开所在目录", lambda: self._open_containing(it))
        menu.exec(self.file_list.viewport().mapToGlobal(pos))

    def _open_containing(self, it):
        import subprocess
        path = os.path.join(self.repo.path, it.path) if self.repo else it.path
        subprocess.Popen(["xdg-open", os.path.dirname(path) or self.repo.path])

    # ---------- Diff ----------

    def show_diff(self, items, rev_from=None, rev_to=None):
        if not self.repo:
            return
        repo = self.repo

        def work():
            if len(items) == 1:
                text = repo.diff(items[0].path, rev_from=rev_from, rev_to=rev_to)
            else:
                text = repo.diff(rev_from=rev_from, rev_to=rev_to)
            return repo.parse_diff(text)

        def done(files):
            names = ", ".join(i.name for i in items[:3])
            viewer = DiffViewer(self, f"Diff — {names}{'…' if len(items) > 3 else ''}",
                                files, self.theme)
            viewer.show()

        self.runner.run(work, on_result=done, on_error=lambda e: self.alert("Diff 失败", str(e)))

    def show_blame(self, item):
        if not self.repo:
            return
        repo = self.repo

        def work():
            return repo.blame(item.path)

        def done(lines):
            c = self.theme.c
            dlg = QDialog(self)
            dlg.setWindowTitle(f"Blame — {item.name}")
            dlg.resize(900, 640)
            lay = QVBoxLayout(dlg)
            txt = QPlainTextEdit()
            txt.setReadOnly(True)
            txt.setFont(QFont("Noto Sans Mono", 9))
            txt.setStyleSheet(
                f"QPlainTextEdit {{ background: {c['bg_panel']}; color: {c['fg']}; border-radius: 8px; }}"
            )
            txt.setPlainText("\n".join(f"r{l.revision:<6} {l.author:<12} {l.text}" for l in lines))
            lay.addWidget(txt)
            dlg.show()

        self.runner.run(work, on_result=done, on_error=lambda e: self.alert("Blame 失败", str(e)))

    # ---------- 操作 ----------

    def on_update(self):
        if not self.repo:
            return
        repo = self.repo
        self.set_status("正在 svn update …")
        self.runner.run(
            repo.update,
            on_result=lambda out: self._after_write("更新", out),
            on_error=lambda e: self._after_fail("更新", e),
        )

    def on_commit(self):
        if not self.repo or not self.items:
            self.alert("提交", "没有可提交的变更", error=False)
            return
        # 只提交当前过滤/目录范围内可见的文件，与列表显示保持一致
        if not self._visible_items():
            self.alert("提交", "当前过滤条件下没有可提交的变更", error=False)
            return
        from .pages.commit_page import CommitPage
        repo = self.repo
        dlg = CommitPage(self, list(self.items), repo, self.theme)
        dlg.exec()
        if dlg.committed_rev:
            self.set_status(f"提交成功 → r{dlg.committed_rev}")
            self.refresh()

    def on_add(self):
        unversioned = [it for it in self.items if it.code == "?"]
        if not unversioned:
            self.alert("添加", "没有未版本控制 (?) 的文件", error=False)
            return
        if not self.confirm("svn add", f"共 {len(unversioned)} 个未版本控制文件，全部添加？"):
            return
        self._do_add(unversioned)

    def _do_add(self, items):
        repo = self.repo
        paths = [i.path for i in items]
        self.runner.run(
            lambda: repo.add(paths),
            on_result=lambda _: self._after_write("添加"),
            on_error=lambda e: self._after_fail("添加", e),
        )

    def _do_revert(self, items):
        repo = self.repo
        paths = [i.path for i in items]
        names = "\n".join(p for p in paths[:10]) + ("\n…" if len(paths) > 10 else "")
        if not self.confirm("svn revert", f"确定还原以下文件的未提交改动？\n\n{names}\n\n此操作不可恢复！"):
            return
        self.runner.run(
            lambda: repo.revert(paths),
            on_result=lambda _: self._after_write("还原"),
            on_error=lambda e: self._after_fail("还原", e),
        )

    def on_cleanup(self):
        if not self.repo:
            return
        self.runner.run(
            self.repo.cleanup,
            on_result=lambda _: self._after_write("清理"),
            on_error=lambda e: self._after_fail("清理", e),
        )

    def on_resolve(self, items=None):
        if not self.repo:
            return
        conflicts = items or [it for it in self.items if it.code == "C"]
        if not conflicts:
            self.alert("解决冲突", "没有冲突 (C) 文件", error=False)
            return
        from .pages.resolve_page import ResolvePage
        ResolvePage(self, self.repo, conflicts, self.theme, on_done=self._after_write_and_refresh).exec()

    def on_lock(self):
        if not self.repo:
            return
        sel = self._selected_items() or [it for it in self.items if it.code in ("M", "A")]
        if not sel:
            self.alert("锁定", "请先在列表中选中文件", error=False)
            return
        dlg = PromptDialog(self, "锁定文件", f"锁定 {len(sel)} 个文件的锁定说明（可空）:", theme=self.theme)
        if not dlg.exec():
            return
        paths = [i.path for i in sel]
        self.runner.run(
            lambda: self.repo.lock(paths, dlg.result or ""),
            on_result=lambda _: self._after_write("锁定"),
            on_error=lambda e: self._after_fail("锁定", e),
        )

    def on_unlock(self):
        if not self.repo:
            return
        sel = self._selected_items()
        if not sel:
            self.alert("解锁", "请先在列表中选中文件", error=False)
            return
        paths = [i.path for i in sel]
        self.runner.run(
            lambda: self.repo.unlock(paths, force=True),
            on_result=lambda _: self._after_write("解锁"),
            on_error=lambda e: self._after_fail("解锁", e),
        )

    def on_ignore(self, names=None):
        if not self.repo:
            return
        if names is None:
            names = [it.name for it in self.items if it.code == "?"]
        if not names:
            self.alert("忽略", "没有可选的文件", error=False)
            return
        dlg = PromptDialog(self, "加入 svn:ignore",
                           "要忽略的文件名（多个用空格分隔）：", preset=" ".join(names[:5]),
                           theme=self.theme)
        if not dlg.exec():
            return
        patterns = dlg.result.split()
        repo = self.repo

        def work():
            return repo.ignore_add(patterns)

        self.runner.run(
            work,
            on_result=lambda _: self._after_write_and_refresh("忽略"),
            on_error=lambda e: self._after_fail("忽略", e),
        )

    # ---------- 分支 / 合并 ----------

    def on_branch_create(self):
        if not self.repo:
            return
        from .pages.branch_page import BranchCreatePage
        BranchCreatePage(self, self.repo, self.theme).exec()

    def on_side_branches(self):
        if not self.repo:
            return
        self.side_branch_page.load(self.repo)
        self.tabs.setCurrentWidget(self.side_branch_page)

    def on_switch(self):
        if not self.repo:
            return
        from .pages.branch_page import SwitchPage
        SwitchPage(self, self.repo, self.theme, on_done=lambda: self._after_write_and_refresh("切换")).exec()

    def on_merge(self):
        if not self.repo:
            return
        from .pages.branch_page import MergePage
        MergePage(self, self.repo, self.theme, on_done=lambda: self._after_write_and_refresh("合并")).exec()

    def on_export(self):
        if not self.repo:
            return
        d = QFileDialog.getExistingDirectory(self, "导出到目录（需为空目录）", self.cfg["last_dir"])
        if not d:
            return
        url = self.repo.info().url
        if not url:
            self.alert("导出", "无法获取仓库 URL")
            return
        repo = self.repo
        self.set_status("正在导出…")
        self.runner.run(
            lambda: repo.export(url, d),
            on_result=lambda _: self._after_write("导出"),
            on_error=lambda e: self._after_fail("导出", e),
        )

    # ---------- 结果处理 ----------

    def _after_write(self, label, out=None):
        self.set_status(f"{label}完成")
        self.refresh()

    def _after_write_and_refresh(self, label):
        self._after_write(label)

    def _after_fail(self, label, e):
        self.log(f"{label}失败: {e}", level="err")
        self.set_status(f"{label}失败")
        self.alert(f"{label}失败", str(e))

    # ---------- 帮助 ----------

    def on_help(self):
        lines = []
        for action_id, (text, _, _) in self.ACTIONS.items():
            sc = self._action_shortcut(action_id) or "（未设置）"
            lines.append(f"{sc:<14} {text}")
        self.alert("快捷键",
                   "\n".join(lines) +
                   "\n\n文件右键: Diff / Blame / 添加 / 还原 / 解决冲突 / 忽略\n"
                   "双击文件: 查看 Diff\n\n"
                   "快捷键可在 文件 → 快捷键 中自定义",
                   error=False)

    def on_shortcut_settings(self):
        from .dialogs import ShortcutDialog
        dlg = ShortcutDialog(self, self.theme)
        if dlg.exec():
            self.apply_shortcuts()
            self.set_status("快捷键已更新")

    def _refresh_repo_menu(self):
        """移除仓库后重建「最近仓库」子菜单（保持原菜单位置）"""
        if getattr(self, "m_repos", None) is None:
            return
        self.m_repos.clear()
        self._rebuild_repo_menu(self.m_repos)
