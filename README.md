# SVN Easy Commit（重构版）— PySide6 桌面 SVN 客户端

基于 PySide6（Qt6）的 Ubuntu SVN 可视化客户端，Termius 风格深色主题。
旧版（CustomTkinter）位于 `../svn-gui`，本版为其架构重写 + 功能扩展。

## 运行

```bash
pip install -r requirements.txt   # PySide6
python3 -m svn_gui                  # 启动
python3 -m svn_gui /path/to/wc      # 直接打开某个工作副本
```

## 安装（Debian / Ubuntu）

`deb` 包内置裁剪版 PySide6 运行时（约 37MB），无需 pip，装完即用：

```bash
./packaging/build-deb.sh            # 打包（生成 svn-gui_<版本>_amd64.deb）
sudo apt install ./svn-gui_1.0.0_amd64.deb
svn-gui                             # 启动，或从应用菜单打开
```

依赖：Python 3.10+、`svn` 命令行客户端（`sudo apt install subversion`）。

## 架构

```
svn_gui/
├── core/                 # 数据层（无 Qt 依赖，可独立测试）
│   ├── svn.py            #   run_svn 命令执行 + 认证重试
│   ├── repo.py           #   SvnRepo：status/log/diff/blame/commit/merge/... 全部返回结构化数据
│   ├── models.py         #   StatusItem / LogEntry / RepoInfo / DiffFile / BlameLine
│   ├── store.py          #   配置 / 凭证 / 提交历史（~/.config/svn_gui/）
│   └── worker.py         #   QThread 后台任务池（TaskRunner）
└── ui/                   # 界面层（PySide6）
    ├── theme.py          #   深/浅色调色板 + 全局 QSS
    ├── main_window.py    #   主窗口：目录树 + 变更列表 + 右侧标签页
    ├── dialogs.py        #   Dialog 基类 / 认证 / 输入弹窗
    ├── diffviewer.py     #   Diff 查看器（多文件、高亮、搜索、+/- 统计）
    └── pages/
        ├── working_copy.py  # 概览页（仓库信息 + 变更统计 + 当前分支）
        ├── log_page.py      # 提交日志（任意两版本 diff）
        ├── commit_page.py   # 提交页（分组勾选 + 模板/历史）
        ├── resolve_page.py  # 冲突解决向导
        ├── side_branch_page.py  # 副分支管理（新建/切换/合并/删除）
        └── branch_page.py   # 分支创建 / switch / merge（带 dry-run 预览）
```

数据层与界面层严格分离：`core` 不 import Qt，`ui` 不解析 svn 文本输出。

## 功能

**基础**
- 打开/管理多个工作副本；检出（checkout）/ 导出（export）
- 变更文件列表：状态徽章（M/A/D/R/C/?…）、按目录树聚合、名称过滤
- 提交：按状态分组勾选、提交说明模板 + 历史、提交前可选自动 update
- Diff 查看器：逐行高亮、多文件切换、±行统计、搜索
- 更新 / 添加 / 还原 / 清理 (cleanup)

**新版增强**
- 提交日志：结构化列表，任意两个版本间 diff，一键复制提交说明
- Blame：按行显示最后修改的版本和作者
- 冲突解决：逐文件选择 mine / theirs / base / working
- 锁定 / 解锁文件（svn lock/unlock）
- 忽略清单（svn:ignore 属性编辑）
- 分支：从任意 URL 创建分支/标签（svn copy --parents）
- 副分支管理：一键在 …/branches/ 下创建副分支（自动推断目标 URL）、
  分支列表（版本/作者/时间）、一键切换、合并到当前位置、删除分支
- 切换分支（svn switch）
- 合并（svn merge）：先 dry-run 预览再应用
- 深/浅色主题即时切换（无需重启）

## 快捷键

| 键 | 功能 |
|---|---|
| Ctrl+O | 打开工作副本 |
| F5 | svn update |
| Ctrl+Enter | 提交 |
| Ctrl+Q | 退出 |

全部快捷键可在 **文件 → 快捷键设置…** 中自定义（点击条目按下新组合键，↺ 恢复默认），
自定义结果保存在 `config.json` 的 `shortcuts` 字段。

文件列表右键：Diff / Blame / 添加 / 还原 / 解决冲突 / 加入忽略。
日志条目右键：与工作副本比对 / 与上一版本比对。

## 配置

`~/.config/svn_gui/`：`config.json`（仓库列表、模板、主题）、
`history.json`（提交说明历史）、`auth.json`（凭证，权限 600）。
