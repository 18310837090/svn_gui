#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用对话框基类 + 认证对话框"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QWidget,
)

from .theme import Theme


class Dialog(QDialog):
    """主题化对话框基类：标题 + body + 底部按钮行（按钮 add 在底部右侧）"""

    def __init__(self, parent, title, width=560, height=420, theme: Theme = None):
        super().__init__(parent)
        self.theme = theme or getattr(parent, "theme", Theme())
        self.setWindowTitle(title)
        self.resize(width, height)
        self.setModal(True)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(20, 16, 20, 16)
        self._root.setSpacing(8)

        lbl = QLabel(title)
        lbl.setObjectName("title")
        self._root.addWidget(lbl)

        self.body = QWidget()
        self._body_layout = QVBoxLayout(self.body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(8)
        self._root.addWidget(self.body, 1)

        self.btnrow = QHBoxLayout()
        self.btnrow.addStretch(1)
        self._root.addLayout(self.btnrow)

    def add_button(self, text, callback, primary=False, danger=False):
        from PySide6.QtWidgets import QPushButton
        b = QPushButton(text)
        if primary:
            b.setObjectName("primary")
        elif danger:
            b.setObjectName("danger")
        b.clicked.connect(callback)
        self.btnrow.addWidget(b)
        return b


class AuthDialog(Dialog):
    """SVN 认证弹窗。exec() 后通过 self.result 取 {"username","password","save"} 或 None"""

    def __init__(self, parent, message, preset_user="", preset_pwd="", theme=None):
        super().__init__(parent, "SVN 认证", 440, 360, theme=theme)
        self.result = None

        msg = QLabel(message[:600])
        msg.setObjectName("dim")
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color: {self.theme.c['red']};")
        self._body_layout.addWidget(msg)

        self._body_layout.addWidget(QLabel("用户名"))
        self.user_entry = QLineEdit()
        if preset_user:
            self.user_entry.setText(preset_user)
        self._body_layout.addWidget(self.user_entry)

        self._body_layout.addWidget(QLabel("密码"))
        self.pwd_entry = QLineEdit()
        self.pwd_entry.setEchoMode(QLineEdit.EchoMode.Password)
        if preset_pwd:
            self.pwd_entry.setText(preset_pwd)
        self._body_layout.addWidget(self.pwd_entry)

        self.save_var = QCheckBox("记住账号密码（明文存于 ~/.config/svn_gui/auth.json）")
        self.save_var.setChecked(bool(preset_user and preset_pwd))
        self._body_layout.addWidget(self.save_var)

        self.user_entry.returnPressed.connect(self.pwd_entry.setFocus)
        self.pwd_entry.returnPressed.connect(self._ok)

        self.add_button("取消", self.reject)
        self.add_button("确 定", self._ok, primary=True)
        self.user_entry.setFocus()

    def _ok(self):
        self.result = {
            "username": self.user_entry.text().strip(),
            "password": self.pwd_entry.text(),
            "save": self.save_var.isChecked(),
        }
        self.accept()


class CheckoutDialog(Dialog):
    """检出对话框：URL + 账号密码一次填完。exec() 后通过 self.result 取
    {"url","username","password","save"} 或 None（取消）"""

    def __init__(self, parent, preset_url="", preset_user="", preset_pwd="", theme=None):
        super().__init__(parent, "检出代码", 520, 320, theme=theme)
        self.result = None

        self._body_layout.addWidget(QLabel("SVN 地址 (URL)"))
        self.url_entry = QLineEdit()
        self.url_entry.setText(preset_url)
        self.url_entry.setPlaceholderText("http://svn.example.com/repos/branch")
        self._body_layout.addWidget(self.url_entry)

        self._body_layout.addWidget(QLabel("用户名"))
        self.user_entry = QLineEdit()
        if preset_user:
            self.user_entry.setText(preset_user)
        self._body_layout.addWidget(self.user_entry)

        self._body_layout.addWidget(QLabel("密码"))
        self.pwd_entry = QLineEdit()
        self.pwd_entry.setEchoMode(QLineEdit.EchoMode.Password)
        if preset_pwd:
            self.pwd_entry.setText(preset_pwd)
        self._body_layout.addWidget(self.pwd_entry)

        self.save_var = QCheckBox("记住账号密码（明文存于 ~/.config/svn_gui/auth.json）")
        self.save_var.setChecked(bool(preset_user and preset_pwd))
        self._body_layout.addWidget(self.save_var)

        self.url_entry.returnPressed.connect(self.user_entry.setFocus)
        self.user_entry.returnPressed.connect(self.pwd_entry.setFocus)
        self.pwd_entry.returnPressed.connect(self._ok)

        self.add_button("取消", self.reject)
        self.add_button("开始检出", self._ok, primary=True)
        if preset_url:
            self.user_entry.setFocus()
        else:
            self.url_entry.setFocus()

    def _ok(self):
        self.result = {
            "url": self.url_entry.text().strip(),
            "username": self.user_entry.text().strip(),
            "password": self.pwd_entry.text(),
            "save": self.save_var.isChecked(),
        }
        self.accept()


class PromptDialog(Dialog):
    """单行输入弹窗（用于新建目录、重命名、锁定说明等）。result 为文本或 None"""

    def __init__(self, parent, title, label="", preset="", theme=None):
        super().__init__(parent, title, 440, 180, theme=theme)
        self.result = None
        if label:
            lbl = QLabel(label)
            lbl.setWordWrap(True)
            self._body_layout.addWidget(lbl)
        self.entry = QLineEdit()
        self.entry.setText(preset)
        self._body_layout.addWidget(self.entry)
        self.entry.returnPressed.connect(self._ok)
        self.add_button("取消", self.reject)
        self.add_button("确 定", self._ok, primary=True)
        self.entry.setFocus()

    def _ok(self):
        self.result = self.entry.text().strip()
        self.accept()


class ShortcutDialog(Dialog):
    """快捷键弹窗：列出全部动作，双击/点击"修改"后按下新组合键。
    确定后把结果写入 main.cfg["shortcuts"] 并保存。"""

    def __init__(self, parent, theme=None):
        super().__init__(parent, "快捷键", 520, 560, theme=theme)
        from PySide6.QtWidgets import QScrollArea, QToolButton, QGridLayout
        from PySide6.QtGui import QKeySequence
        main = parent
        self._pending = {}   # action_id -> 新快捷键串（未保存）

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self._rows = {}      # action_id -> (lbl_sc, btn_reset)

        for row, (action_id, (text, default, _slot)) in enumerate(main.ACTIONS.items()):
            cur = main._action_shortcut(action_id)

            lbl_name = QLabel(text)
            lbl_name.setStyleSheet("border: none;")
            grid.addWidget(lbl_name, row, 0)

            lbl_sc = QLabel(cur or "（未设置）")
            lbl_sc.setStyleSheet(
                f"border: 1px solid {self.theme.c['border']}; border-radius: 4px;"
                f"background: {self.theme.c['bg_input']}; padding: 3px 10px;"
            )
            lbl_sc.setCursor(Qt.PointingHandCursor)
            lbl_sc.setToolTip("点击后按下新的快捷键")
            grid.addWidget(lbl_sc, row, 1)

            btn_reset = QToolButton()
            btn_reset.setText("↺")
            btn_reset.setToolTip(f"恢复默认 ({default or '无'})")
            btn_reset.setStyleSheet("QToolButton{border:none;padding:2px 6px;border-radius:4px;}"
                                    "QToolButton:hover{background:palette(highlight);}")
            grid.addWidget(btn_reset, row, 2)

            self._rows[action_id] = (lbl_sc, btn_reset)

            def start_capture(_checked=False, aid=action_id):
                lbl = self._rows[aid][0]
                lbl.setText("按下组合键… (Esc 取消)")
                self._capturing = aid

            def reset(_checked=False, aid=action_id, dft=default):
                self._pending[aid] = dft
                lbl = self._rows[aid][0]
                lbl.setText(dft or "（未设置）")

            lbl_sc.mousePressEvent = lambda _e, s=start_capture: s()
            btn_reset.clicked.connect(reset)

        scroll = QScrollArea()
        scroll.setWidget(grid_host)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._body_layout.addWidget(scroll, 1)

        hint = QLabel("点击快捷键框后按下新组合键；↺ 恢复默认。灰色“未设置”表示该动作无快捷键。")
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {self.theme.c['fg_dim']}; border: none;")
        self._body_layout.addWidget(hint)

        self.add_button("恢复全部默认", self._reset_all)
        self.add_button("取消", self.reject)
        self.add_button("保 存", self._save, primary=True)
        self._capturing = None

    def keyPressEvent(self, ev):
        """处于捕获状态时，把按键翻译为快捷键串"""
        from PySide6.QtGui import QKeySequence
        aid = getattr(self, "_capturing", None)
        if not aid:
            super().keyPressEvent(ev)
            return
        k = ev.key()
        mods = ev.modifiers()
        if k in (Qt.Key.Key_Escape,):
            # Esc：若没有修饰键则取消捕获，否则算作快捷键的一部分（如 Ctrl+Esc）
            if mods == Qt.KeyboardModifier.NoModifier:
                self._rows[aid][0].setText(self._pending.get(aid) or
                                           self._current_text(aid))
                self._capturing = None
                return
        mods_i = int(mods.value) if hasattr(mods, "value") else int(mods)
        seq = QKeySequence(mods_i | int(k))
        text = seq.toString(QKeySequence.SequenceFormat.NativeText) or \
               seq.toString(QKeySequence.SequenceFormat.PortableText)
        if text:
            self._pending[aid] = text
            self._rows[aid][0].setText(text)
        self._capturing = None

    def _current_text(self, aid):
        main = self.parent()
        return main._action_shortcut(aid)

    def _reset_all(self):
        self._pending = {aid: dft for aid, (_t, dft, _s) in
                         self.parent().ACTIONS.items()}
        for aid, dft in self._pending.items():
            self._rows[aid][0].setText(dft or "（未设置）")

    def _save(self):
        main = self.parent()
        custom = dict(main.cfg.data.get("shortcuts", {}))
        for aid, val in self._pending.items():
            if val == main.ACTIONS[aid][1]:
                custom.pop(aid, None)   # 与默认一致则不占配置
            else:
                custom[aid] = val
        main.cfg.data["shortcuts"] = custom
        main.cfg.save()
        self.accept()
