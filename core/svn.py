#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SVN 命令执行 — run_svn 与认证处理（无 UI 依赖，经回调上抛认证请求）"""

import os
import subprocess


class SvnError(Exception):
    def __init__(self, rc, err, out=""):
        self.rc = rc
        self.err = err
        self.out = out
        super().__init__(err or out or f"svn 失败 (rc={rc})")


_AUTH_KEYWORDS = (
    "E170013", "E215004", "E175013",
    "Authentication failed", "authorization failed",
    "认证失败", "密码", "Cannot authenticate", "禁止访问",
)


def _need_auth(rc, combined):
    return any(k in combined for k in _AUTH_KEYWORDS)


def run_svn(args, cwd=None, timeout=120, auth_prompt=None):
    """执行 svn 命令，返回 (rc, stdout, stderr)。
    auth_prompt: 回调 (err_text) -> {"username","password","save","repo_url"} | None
    认证失败时调用，由上层弹窗询问后带凭证重试（最多 2 次）。"""
    env = dict(os.environ)
    env["LC_ALL"] = "C.UTF-8"

    def _run(extra):
        cmd = ["svn", "--non-interactive"] + extra
        try:
            p = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout, env=env)
            return (p.returncode,
                    p.stdout.decode("utf-8", errors="replace"),
                    p.stderr.decode("utf-8", errors="replace"))
        except FileNotFoundError:
            return 127, "", "找不到 svn 命令，请先安装: sudo apt install subversion"
        except subprocess.TimeoutExpired:
            return 124, "", "svn 命令执行超时"

    rc, out, err = _run(list(args))
    if rc == 0 or not auth_prompt:
        return rc, out, err

    for _ in range(2):
        combined = out + err
        if not _need_auth(rc, combined):
            return rc, out, err
        cred = auth_prompt(combined)
        if not cred or not cred.get("username"):
            return rc, out, err  # 用户取消
        retry = ["--username", cred["username"], "--password", cred.get("password", ""),
                 "--trust-server-cert"] + list(args)
        rc, out, err = _run(retry)
        if rc == 0:
            if cred.get("save") and cred.get("repo_url"):
                # 保存动作由上层完成（core 不碰磁盘凭证），这里只报告成功
                cred["_succeeded"] = True
            return rc, out, err
    return rc, out, err
