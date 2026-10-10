#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SvnRepo — 工作副本操作层。全部返回结构化数据（models），失败抛 SvnError。"""

import os
import re
import xml.etree.ElementTree as ET

from .svn import run_svn, SvnError, _need_auth
from .models import StatusItem, LogEntry, RepoInfo, DiffFile, BlameLine


_XML_ITEM_TO_CODE = {
    "modified": "M", "added": "A", "deleted": "D", "replaced": "R",
    "conflicted": "C", "missing": "!", "unversioned": "?", "external": "X",
    "obstructed": "~", "ignored": "I", "replaced": "R", "incomplete": "!",
}


class SvnRepo:
    def __init__(self, path, auth_prompt=None):
        self.path = os.path.abspath(path)
        self.auth_prompt = auth_prompt

    # ---------- 基础查询 ----------

    def _run(self, args, cwd=None, timeout=120):
        rc, out, err = run_svn(args, cwd=cwd or self.path, timeout=timeout, auth_prompt=self.auth_prompt)
        if rc != 0:
            raise SvnError(rc, err, out)
        return out

    def is_working_copy(self):
        if not os.path.isdir(self.path):
            return False
        rc, _, _ = run_svn(["info", self.path], timeout=15)
        return rc == 0

    def info(self) -> RepoInfo:
        out = self._run(["info", self.path], timeout=15)
        d = {}
        for line in out.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                d[k.strip()] = v.strip()
        return RepoInfo(
            url=d.get("URL", ""),
            root=d.get("Repository Root", d.get("版本库根", "")),
            revision=d.get("Revision", d.get("版本", "")),
            uuid=d.get("Repository UUID", d.get("版本库 UUID", "")),
            author=d.get("Last Changed Author", d.get("最后修改作者", "")),
            schedule=d.get("Schedule", d.get("调度", "normal")),
            raw=d,
        )

    # ---------- 状态 ----------

    def status(self) -> list:
        """svn status --xml → [StatusItem]（path 相对工作副本根）"""
        out = self._run(["status", "--xml", self.path], timeout=120)
        items = []
        try:
            root = ET.fromstring(out)
            for target in root.findall("target"):
                for entry in target.findall("entry"):
                    p = entry.get("path", "")
                    wc = entry.find("wc-status")
                    if wc is None:
                        continue
                    item_name = wc.get("item", "none")
                    code = _XML_ITEM_TO_CODE.get(item_name)
                    if code is None:
                        continue
                    item = StatusItem(path=p, code=code)
                    if wc.get("copied"):
                        item.desc += "（来自复制）"
                    items.append(item)
        except ET.ParseError:
            return self._status_text()
        return self._relativize(items)

    def _relativize(self, items):
        """把绝对路径归一为相对 self.path 的路径"""
        if not items:
            return items
        base = self.path.rstrip(os.sep) + os.sep
        for it in items:
            if os.path.isabs(it.path) and it.path.startswith(base):
                it.path = it.path[len(base):]
        return items

    def _status_text(self) -> list:
        rc, out, err = run_svn(["status", self.path], timeout=60)
        if rc != 0:
            raise SvnError(rc, err, out)
        items = []
        for line in out.splitlines():
            if not line.strip():
                continue
            code = line[0] if line[0] != " " else (line[1] if len(line) > 1 else " ")
            if code == " ":
                continue
            path = line[7:].strip()
            if path:
                items.append(StatusItem(path=path, code=code))
        return items

    # ---------- Diff ----------

    def diff(self, path=None, rev_from=None, rev_to=None, repo_url=None) -> str:
        args = ["diff", "--internal-diff"]
        if rev_from and rev_to:
            args += ["-r", f"{rev_from}:{rev_to}"]
        elif rev_from:
            args += ["-r", rev_from]
        if repo_url:
            args.append(repo_url)
        elif path:
            args.append(path)
        return self._run(args, timeout=300)

    def parse_diff(self, text) -> list:
        """把 svn diff 输出解析成 [DiffFile]"""
        files = []
        cur = None
        for line in text.splitlines():
            if line.startswith("Index: "):
                cur = DiffFile(path=line[7:].strip())
                files.append(cur)
                cur.lines.append(("meta", line))
            elif cur is not None:
                if line.startswith(("+++", "---")):
                    cur.lines.append(("head", line))
                elif line.startswith("@@"):
                    cur.lines.append(("hunk", line))
                elif line.startswith("+"):
                    cur.lines.append(("add", line))
                elif line.startswith("-"):
                    cur.lines.append(("del", line))
                elif line.startswith("====") or line.startswith("Property changes"):
                    cur.lines.append(("meta", line))
                else:
                    cur.lines.append(("", line))
        return files

    def diff_files(self, path=None, rev_from=None, rev_to=None, repo_url=None) -> list:
        return self.parse_diff(self.diff(path, rev_from, rev_to, repo_url))

    # ---------- 日志 ----------

    def log(self, limit=100, rev_range=None, target=None) -> list:
        """svn log --xml → [LogEntry]。优先 HEAD（联网），失败降级 BASE（离线）。"""
        args = ["log", "--xml", "-l", str(limit), "-v"]
        if rev_range:
            args += ["-r", rev_range]
        else:
            args += ["-r", "HEAD:1"]
        args.append(target or self.path)

        out, last_err = self._log_run(args, timeout=60)
        if out is None:
            # 降级 BASE:1（不联网）
            args[args.index("HEAD:1")] = "BASE:1"
            out, last_err = self._log_run(args, timeout=60)
            if out is None:
                raise SvnError(1, f"svn log 失败（联网与离线均失败）\n{last_err or ''}".strip())
        return self._parse_log(out)

    def _log_run(self, args, timeout):
        # 日志也带上已保存的凭证：服务器要求认证时 HEAD/BASE 都会失败，
        # 静默失败只会看到"联网与离线均失败"，这里用 app 保存的账号重试
        rc, out, err = run_svn(args, timeout=timeout)
        if rc == 0:
            return out, None
        if _need_auth(rc, out + err):
            cred = self._saved_cred()
            if cred:
                rc2, out2, err2 = run_svn(
                    ["--username", cred["username"], "--password", cred.get("password", "")] + args,
                    timeout=timeout)
                if rc2 == 0:
                    return out2, None
        return None, (err or out).strip()

    def _saved_cred(self):
        """从 app 凭证文件里找当前仓库 URL 对应的账号（core 层直接读，避免弹窗）"""
        try:
            from .store import load_auth
            auth = load_auth()
            url = self.info().url
            return auth.get(url) or auth.get("_last_user")
        except Exception:
            return None

    def _parse_log(self, xml_text) -> list:
        entries = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return entries
        for le in root.findall("logentry"):
            paths = []
            lp = le.find("paths")
            if lp is not None:
                for p in lp.findall("path"):
                    paths.append((p.get("action", ""), p.text or ""))
            entries.append(LogEntry(
                revision=int(le.get("revision", "0")),
                author=le.findtext("author", ""),
                date=(le.findtext("date", "") or "").replace("T", " ").split(".")[0],
                message=le.findtext("msg", ""),
                changed_paths=paths,
            ))
        return entries

    # ---------- Blame ----------

    def blame(self, path) -> list:
        """svn blame 文本输出 → [BlameLine]（文本格式自含行内容，比 XML 更省事）"""
        out = self._run(["blame", path], timeout=120)
        lines = []
        for ln in out.splitlines():
            m = re.match(r"\s*(\d+)\s+(\S+)\s?(.*)", ln)
            if m:
                lines.append(BlameLine(int(m.group(1)), m.group(2), m.group(3)))
        return lines

    # ---------- 写操作 ----------

    def update(self, path=None, revision=None) -> str:
        args = ["update"]
        if revision:
            args += ["-r", revision]
        args.append(path or self.path)
        return self._run(args, timeout=1800)

    def checkout(self, url, target_dir, revision=None, depth="infinity",
                 username=None, password=None) -> str:
        args = ["checkout", url]
        if revision:
            args += ["-r", revision]
        args += ["--depth", depth, target_dir]
        if username:
            args = ["--username", username, "--password", password or ""] + args
        rc, out, err = run_svn(args, timeout=3600, auth_prompt=self.auth_prompt)
        if rc != 0:
            raise SvnError(rc, err, out)
        return out

    def add(self, paths, force=True, parents=False) -> str:
        args = ["add"]
        if force:
            args.append("--force")
        if parents:
            args.append("--parents")
        args += paths if isinstance(paths, list) else [paths]
        return self._run(args, timeout=120)

    def revert(self, paths, recursive=True) -> str:
        args = ["revert"]
        if recursive:
            args.append("-R")
        args += paths if isinstance(paths, list) else [paths]
        return self._run(args, timeout=120)

    def commit(self, paths, message) -> int:
        """返回提交后的版本号（解析失败返回 -1）"""
        args = ["commit"] + list(paths) + ["-m", message]
        out = self._run(args, timeout=1800)
        m = re.search(r"提交后的版本为 (\d+)|committed revision (\d+)", out)
        return int(m.group(1) or m.group(2)) if m else -1

    def delete(self, paths, force=False) -> str:
        args = ["delete"]
        if force:
            args.append("--force")
        args += paths if isinstance(paths, list) else [paths]
        return self._run(args, timeout=60)

    def mkdir(self, url_or_path, message=None) -> str:
        if message:
            return self._run(["mkdir", url_or_path, "-m", message], timeout=120)
        return self._run(["mkdir", url_or_path], timeout=120)

    def copy(self, src, dst, message=None) -> str:
        """工作副本内复制（记历史）或 URL 复制（建分支，父目录需存在或加 --parents）"""
        args = ["copy", src, dst, "--parents"]
        if message:
            args += ["-m", message]
        return self._run(args, timeout=120)

    def move(self, src, dst) -> str:
        return self._run(["move"] + ([src] if isinstance(src, str) else src) + [dst], timeout=120)

    def switch(self, url, revision=None) -> str:
        args = ["switch", url]
        if revision:
            args += ["-r", revision]
        args.append(self.path)
        return self._run(args, timeout=1800)

    def merge(self, source, rev_range=None, dry_run=False, record_only=False) -> str:
        args = ["merge", source]
        if rev_range:
            args += ["-r", rev_range]
        args.append(".")
        if dry_run:
            args.append("--dry-run")
        if record_only:
            args.append("--record-only")
        return self._run(args, timeout=600)

    def mergeinfo(self, source=None) -> str:
        args = ["mergeinfo", "--show-revs", "eligible"]
        if source:
            args.append(source)
        return self._run(args, timeout=120)

    def resolve(self, path, accept="working") -> str:
        """accept: working / base / mine-full / theirs-full"""
        return self._run(["resolve", "--accept", accept, path], timeout=60)

    def cleanup(self) -> str:
        return self._run(["cleanup", self.path], timeout=600)

    def lock(self, paths, message="") -> str:
        args = ["lock"]
        if message:
            args += ["-m", message]
        args += paths if isinstance(paths, list) else [paths]
        return self._run(args, timeout=60)

    def unlock(self, paths, force=False) -> str:
        args = ["unlock"]
        if force:
            args.append("--force")
        args += paths if isinstance(paths, list) else [paths]
        return self._run(args, timeout=60)

    def propset(self, name, value, paths, recursive=False) -> str:
        args = ["propset", name, value]
        if recursive:
            args.append("-R")
        args += paths if isinstance(paths, list) else [paths]
        return self._run(args, timeout=60)

    def propdel(self, name, paths, recursive=False) -> str:
        args = ["propdel", name]
        if recursive:
            args.append("-R")
        args += paths if isinstance(paths, list) else [paths]
        return self._run(args, timeout=60)

    def proplist(self, path, verbose=False) -> list:
        args = ["proplist"]
        if verbose:
            args.append("-v")
        args.append(path)
        out = self._run(args, timeout=60)
        props = []
        for line in out.splitlines():
            line = line.strip()
            if line and not line.startswith(("Properties on", "属性的")):
                props.append(line)
        return props

    def propget(self, name, path) -> str:
        return self._run(["propget", name, path], timeout=60).rstrip("\n")

    def export(self, url, target_dir, revision=None) -> str:
        args = ["export", url]
        if revision:
            args += ["-r", revision]
        args.append(target_dir)
        return self._run(args, timeout=3600)

    def ignore_add(self, patterns, directory="."):
        """把 pattern 加入目录的 svn:ignore 属性"""
        existing = []
        try:
            cur = self.propget("svn:ignore", directory)
            existing = [l for l in cur.splitlines() if l.strip()]
        except SvnError:
            pass
        new = [p for p in patterns if p and p not in existing]
        if not new:
            return existing
        merged = existing + new
        self.propset("svn:ignore", "\n".join(merged), directory)
        return merged

    # ---------- 副分支 ----------

    def ls_remote(self, url) -> list:
        """svn ls --xml <url> → [(name, revision, author, date)]，按名排序。
        url 不存在时抛 SvnError（如 branches/ 目录还没建）。"""
        out = self._run(["ls", "--xml", url], timeout=60)
        items = []
        try:
            root = ET.fromstring(out)
        except ET.ParseError:
            return items
        for e in root.findall(".//entry"):
            name = (e.findtext("name") or e.get("path", "")).rstrip("/").split("/")[-1]
            commit = e.find("commit")
            if commit is None:
                items.append((name, "", "", ""))
                continue
            items.append((
                name,
                commit.get("revision", ""),
                commit.findtext("author", ""),
                (commit.findtext("date", "") or "").replace("T", " ").split(".")[0],
            ))
        return items

    def delete_remote(self, url, message=None) -> str:
        args = ["rm", url]
        if message:
            args += ["-m", message]
        return self._run(args, timeout=120)


def branches_base(url, repo_root=""):
    """推断 branches/ 基目录 URL：
    trunk → 同级的 /branches；已在 /branches/<x>/… 下 → /branches 段；兜底用仓库根拼 /branches。"""
    if not url:
        return ""
    for pat in ("/trunk", "/trunk/"):
        if pat in url:
            return url.split("/trunk")[0] + "/branches"
    if "/branches/" in url:
        return url.split("/branches/")[0] + "/branches"
    if url.rstrip("/").endswith("/branches"):
        return url.rstrip("/")
    if repo_root and url.startswith(repo_root):
        return repo_root.rstrip("/") + "/branches"
    base = url.rsplit("/", 1)[0]
    return base + "/branches"


def current_branch_name(url):
    """当前 URL 所在分支名：trunk → 'trunk'；branches/<x>/… → '<x>'；其它返回 ''"""
    if not url:
        return ""
    if "/trunk" in url:
        return "trunk"
    if "/branches/" in url:
        rest = url.split("/branches/", 1)[1]
        return rest.split("/", 1)[0] or ""
    return ""


def infer_branch_target(url, name, repo_root=""):
    """按名字推断新副分支的目标 URL（调用方仍允许用户修改）"""
    if not url or not name:
        return ""
    return branches_base(url, repo_root) + "/" + name.strip().strip("/")

