#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据模型 — 状态、日志、信息等结构化数据（无 UI 依赖）"""

from dataclasses import dataclass, field


# 状态码 -> 中文说明 / 颜色角色
STATUS_DESC = {
    "A": "新增", "M": "修改", "D": "删除", "R": "替换", "C": "冲突",
    "!": "丢失", "?": "未版本控制", "X": "外部", "~": "类型变更", "I": "忽略",
}

# 颜色角色（UI 层按主题解析成具体颜色）
STATUS_ROLE = {
    "A": "green", "M": "yellow", "D": "red", "R": "purple", "C": "red",
    "!": "red", "?": "gray", "X": "gray", "~": "yellow", "I": "gray",
}


@dataclass
class StatusItem:
    path: str            # 相对工作副本根的路径
    code: str            # 状态码 A/M/D/R/C/!/?
    desc: str = ""
    role: str = "gray"
    added: bool = False
    missing: bool = False

    def __post_init__(self):
        self.desc = self.desc or STATUS_DESC.get(self.code, self.code)
        self.role = STATUS_ROLE.get(self.code, "gray")
        self.added = self.code == "?"
        self.missing = self.code == "!"

    @property
    def name(self):
        import os
        return os.path.basename(self.path) or self.path

    @property
    def dirname(self):
        import os
        return os.path.dirname(self.path)


@dataclass
class LogEntry:
    revision: int
    author: str = ""
    date: str = ""
    message: str = ""
    changed_paths: list = field(default_factory=list)   # [(action, path)]


@dataclass
class RepoInfo:
    url: str = ""
    root: str = ""       # 仓库根 URL
    revision: str = ""
    uuid: str = ""
    author: str = ""
    schedule: str = ""   # "normal" / "add" / "replace" / "delete"
    depth: str = ""
    raw: dict = field(default_factory=dict)  # svn info 原始键值


@dataclass
class DiffFile:
    """一个 diff 输出中解析出的单文件段落"""
    path: str = ""       # Index: 后的路径
    lines: list = field(default_factory=list)  # [(tag, text)] tag: add/del/hunk/head/meta/""


@dataclass
class BlameLine:
    revision: int
    author: str = ""
    text: str = ""
