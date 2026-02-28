# overleaf-ce-mcp

面向自建 Overleaf Community Edition 的 MCP 服务原型。

核心思路：
- 通过 `overleaf-sync-ce` (`ols`) 完成 CE 双向同步。
- 在本地生成/维护出版社 LaTeX 模板稿件（含 Ocean Engineering 模板骨架）。
- 通过 MCP 工具在 AI 会话里直接完成“写稿 -> 同步 -> 编译”。

## 1. 安装

```bash
cd /root/overleaf-ce-mcp
/root/miniconda3/bin/python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install .
```

说明：
- 需要 Python `>=3.11`。本机建议直接使用 `miniconda` 自带 Python。
- 也可以直接执行 `bash scripts/bootstrap.sh` 自动完成安装。

安装外部依赖（按需）：

```bash
# Overleaf CE 同步工具
pip install overleaf-sync-ce

# 本地编译（可选）
sudo apt-get update
sudo apt-get install -y texlive-latex-base texlive-latex-extra latexmk
```

## 2. 启动

```bash
source /root/overleaf-ce-mcp/.venv/bin/activate
overleaf-ce-mcp
```

## 3. 可用工具

- `check_environment`: 检查 `ols/latexmk/zip/unzip` 是否可用
- `ols_login`: 执行 Overleaf 登录并生成 `.olauth`
- `ols_list_projects`: 列出账号项目
- `ols_sync`: 双向/单向同步本地项目目录
- `init_manuscript_from_template`: 初始化模板稿件目录
- `write_file`: 写入或覆盖文本文件
- `compile_latex`: 本地调用 `latexmk` 编译
- `package_project_zip`: 打包项目目录
- `upload_project_zip`: 将 zip 稿件上传到 CE 并创建新项目（通用上传）
- `upload_project_dir`: 将本地目录按通用规则打包后上传到 CE（创建新项目或覆盖已有项目）
- `health_check_project`: 检查项目可见性与可编译性
- `apply_compat_patches`: 手动触发兼容补丁（通常无需手动执行）

## 4. 模板

内置模板：
- `ocean-engineering-oa`

模板位置：
- `templates/ocean-engineering-oa`

## 5. 通用上传说明

新增上传流程默认使用 CE 的 `/project/new/upload` 接口，避免依赖旧版 socket/file-tree API 差异。

上传时会自动：
- 兼容 `overleaf.sid` / `sharelatex.sid` 两类会话 cookie。
- 自动刷新 `ol-csrfToken`。
- 以 multipart 方式提交 `qqfile`，并补充 `name/type` 元数据（提升 CE 兼容性）。

目录上传默认排除：
- `.git`、`__pycache__`
- `*.aux`、`*.log`、`*.pdf`、`*.zip` 等编译产物

可通过 `exclude_globs`（字符串数组）额外追加排除规则。

### `upload_project_dir` 模式

- 新建项目模式（默认）：
  - 不传 `target_project`
  - 行为：打包 -> 上传 -> 创建新项目

- 已有项目模式：
  - 传 `target_project`
  - `existing_project_strategy=merge`：合并更新，不主动删除远端多余文件
  - `existing_project_strategy=replace`：按本地覆盖远端（会删除远端本地不存在的文件）
  - 同步安全护栏：当传 `project_name` 且 `workspace_path` 下存在同名子目录时，会自动收敛到该子目录，避免误同步整个 workspace。

- `dry_run=true`：
  - 只输出打包与执行计划，不执行实际上传/同步。

- 健康检查：
  - `health_check=true`（默认）会在操作完成后检查项目可用性
  - `compile_check=true`（默认）会触发编译并返回 PDF 可用性

## 6. 兼容补丁机制

为兼容新旧 CE 的会话与 API 差异，服务会自动应用补丁到依赖：
- `olsync`（cookie 名、project infos 结构、非交互行为等）
- `socketIO_client`（异常兼容）

补丁文件位于：
- `overleaf_ce_mcp/vendor_patches/`

默认会在环境检查和 `ols` 调用前自动确保补丁生效；必要时可手动调用 `apply_compat_patches`。
