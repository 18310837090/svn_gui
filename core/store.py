#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置 / 凭证 / 提交历史存储（JSON 文件，~/.config/svn_gui/）"""

import json
import os
import shutil

_CONFIG_BASE = os.path.expanduser("~/.config")
CONFIG_DIR = os.path.join(_CONFIG_BASE, "svn_gui")
_OLD_CONFIG_DIR = os.path.join(_CONFIG_BASE, "svn-easy-commit")


def _migrate_old_dir():
    """旧版配置目录 svn-easy-commit -> svn_gui，一次性搬迁。"""
    if not os.path.isdir(_OLD_CONFIG_DIR) or os.path.exists(CONFIG_DIR):
        return
    try:
        shutil.move(_OLD_CONFIG_DIR, CONFIG_DIR)
    except Exception:
        pass


_migrate_old_dir()
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
HISTORY_FILE = os.path.join(CONFIG_DIR, "history.json")
AUTH_FILE = os.path.join(CONFIG_DIR, "auth.json")


def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class Config:
    DEFAULTS = {
        "last_dir": os.path.expanduser("~"),
        "message_templates": ["修复: ", "新增: ", "优化: ", "重构: ", "文档: "],
        "auto_update_before_commit": True,
        "repos": [],
        "theme": "dark",
        "external_diff_cmd": "",   # 如: "meld {left} {right}"
        "window_geometry": "",
        "shortcuts": {},           # 动作 id -> 快捷键字符串，空串表示禁用
    }

    def __init__(self):
        self.data = dict(self.DEFAULTS)
        self.data.update(_load(CONFIG_FILE, {}))

    def save(self):
        _save(CONFIG_FILE, self.data)

    def __getitem__(self, key):
        return self.data.get(key, self.DEFAULTS.get(key))

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()

    # 常用属性

    @property
    def repos(self):
        return self.data.get("repos", [])

    def add_repo(self, path):
        path = os.path.abspath(path)
        repos = self.repos
        if any(r["path"] == path for r in repos):
            return
        name = os.path.basename(path) or path
        repos.insert(0, {"name": name, "path": path})
        self.data["repos"] = repos[:20]
        self.save()

    def remove_repo(self, path):
        self.data["repos"] = [r for r in self.repos if r["path"] != path]
        self.save()

    @property
    def templates(self):
        return self.data.get("message_templates", [])


def load_history():
    return _load(HISTORY_FILE, [])


def push_history(message):
    if not message.strip():
        return
    h = load_history()
    if message in h:
        h.remove(message)
    h.insert(0, message)
    _save(HISTORY_FILE, h[:50])


def load_auth():
    return _load(AUTH_FILE, {})


def save_auth(data):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.chmod(AUTH_FILE, 0o600)
    except Exception:
        pass
