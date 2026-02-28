"""Overleaf CE MCP 服务入口。"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .compat import ensure_compat_patches
from .sync import command_exists, ols_list, ols_login, ols_sync, run_command
from .template import init_template_project, list_templates
from .upload import (
    find_project_by_name,
    health_check_project,
    package_project_for_upload,
    upload_zip_as_new_project,
)


server = Server("overleaf-ce-mcp")


def _dump(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_globs(value: Any) -> List[str]:
    """将用户输入解析为排除模式列表。兼容数组与逗号分隔字符串。"""
    if value is None:
        return []
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                out.append(s)
        return out
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return []


def _collect_env_status() -> Dict[str, Any]:
    patch_info = ensure_compat_patches()
    return {
        "python": sys.version.split()[0],
        "commands": {
            "ols": command_exists("ols"),
            "latexmk": command_exists("latexmk"),
            "zip": command_exists("zip"),
            "unzip": command_exists("unzip"),
        },
        "templates": list_templates(),
        "compat_patches": patch_info,
    }


@server.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="check_environment",
            description="检查当前环境是否安装 ols/latexmk/zip/unzip，以及可用模板列表。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="ols_login",
            description="执行 `ols login`，用于 CE 登录并生成 .olauth。首次登录通常需要图形界面交互。",
            inputSchema={
                "type": "object",
                "properties": {
                    "store_path": {"type": "string", "description": ".olauth 保存路径（可选）"},
                    "ce_url": {"type": "string", "description": "CE 地址（可选）"},
                },
            },
        ),
        Tool(
            name="ols_list_projects",
            description="执行 `ols list`，列出账号项目。",
            inputSchema={
                "type": "object",
                "properties": {
                    "store_path": {"type": "string", "description": ".olauth 路径（可选）"},
                    "ce_url": {"type": "string", "description": "CE 地址（可选）"},
                    "verbose": {"type": "boolean", "description": "是否输出详细信息"},
                },
            },
        ),
        Tool(
            name="ols_sync",
            description="执行 `ols` 同步。mode 支持 bidirectional/local-only/remote-only。",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_path": {
                        "type": "string",
                        "description": "本地项目目录（可选，不传则使用当前目录）",
                    },
                    "project_name": {"type": "string", "description": "远端项目名（可选）"},
                    "ce_url": {"type": "string", "description": "CE 地址（可选）"},
                    "mode": {
                        "type": "string",
                        "enum": ["bidirectional", "local-only", "remote-only"],
                        "description": "同步模式",
                    },
                    "store_path": {"type": "string", "description": ".olauth 路径（可选）"},
                    "olignore": {"type": "string", "description": ".olignore 路径（可选）"},
                    "delete_policy": {
                        "type": "string",
                        "enum": ["d", "r", "i"],
                        "description": "非交互删除策略：d删远端、r回滚本地、i忽略",
                    },
                    "verbose": {"type": "boolean", "description": "是否输出详细信息"},
                },
            },
        ),
        Tool(
            name="init_manuscript_from_template",
            description="按模板初始化论文目录，当前内置 ocean-engineering-oa。",
            inputSchema={
                "type": "object",
                "properties": {
                    "template_name": {"type": "string", "description": "模板名称"},
                    "target_dir": {"type": "string", "description": "目标空目录"},
                    "title": {"type": "string", "description": "论文标题"},
                    "authors": {"type": "string", "description": "作者字符串（逗号分隔）"},
                    "corresponding_email": {"type": "string", "description": "通讯作者邮箱"},
                    "keywords": {"type": "string", "description": "关键词字符串（逗号分隔）"},
                },
                "required": ["target_dir"],
            },
        ),
        Tool(
            name="write_file",
            description="写入或覆盖文本文件（UTF-8）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件绝对路径"},
                    "content": {"type": "string", "description": "文件内容"},
                },
                "required": ["file_path", "content"],
            },
        ),
        Tool(
            name="compile_latex",
            description="在项目目录执行 latexmk 编译。",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "项目目录"},
                    "main_tex": {"type": "string", "description": "主 tex 文件，默认 main.tex"},
                },
                "required": ["project_dir"],
            },
        ),
        Tool(
            name="package_project_zip",
            description="将项目目录打包成 zip 文件。",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "项目目录"},
                    "output_zip": {"type": "string", "description": "输出 zip 路径（可选）"},
                },
                "required": ["project_dir"],
            },
        ),
        Tool(
            name="upload_project_zip",
            description="将 zip 稿件上传到 Overleaf CE，并创建新项目（通用上传方式）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ce_url": {"type": "string", "description": "Overleaf CE 地址，如 http://host:17880"},
                    "zip_path": {"type": "string", "description": "待上传 zip 的绝对路径"},
                    "store_path": {"type": "string", "description": ".olauth 路径（可选，默认 ~/.olauth）"},
                    "timeout": {"type": "integer", "description": "上传超时秒数（可选，默认 300）"},
                    "health_check": {"type": "boolean", "description": "上传后是否做健康检查（默认 true）"},
                    "compile_check": {"type": "boolean", "description": "健康检查时是否触发编译（默认 true）"},
                },
                "required": ["ce_url", "zip_path"],
            },
        ),
        Tool(
            name="upload_project_dir",
            description="将本地项目目录按通用规则打包并上传到 Overleaf CE（创建新项目）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ce_url": {"type": "string", "description": "Overleaf CE 地址，如 http://host:17880"},
                    "project_dir": {"type": "string", "description": "本地项目目录"},
                    "store_path": {"type": "string", "description": ".olauth 路径（可选，默认 ~/.olauth）"},
                    "output_zip": {"type": "string", "description": "输出 zip 路径（可选）"},
                    "exclude_globs": {"type": "array", "items": {"type": "string"}, "description": "额外排除规则"},
                    "dry_run": {"type": "boolean", "description": "只预览打包/同步计划，不执行上传"},
                    "target_project": {"type": "string", "description": "目标已有项目名（可选，不传则创建新项目）"},
                    "existing_project_strategy": {
                        "type": "string",
                        "enum": ["merge", "replace"],
                        "description": "已有项目策略：merge 合并，replace 远端按本地覆盖",
                    },
                    "timeout": {"type": "integer", "description": "上传超时秒数（可选，默认 300）"},
                    "health_check": {"type": "boolean", "description": "完成后是否做健康检查（默认 true）"},
                    "compile_check": {"type": "boolean", "description": "健康检查时是否触发编译（默认 true）"},
                    "verbose": {"type": "boolean", "description": "同步时是否输出详细日志（默认 false）"},
                },
                "required": ["ce_url", "project_dir"],
            },
        ),
        Tool(
            name="health_check_project",
            description="检查 CE 项目是否可见并可编译，返回 PDF 结果信息。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ce_url": {"type": "string", "description": "Overleaf CE 地址"},
                    "store_path": {"type": "string", "description": ".olauth 路径（可选，默认 ~/.olauth）"},
                    "project_name": {"type": "string", "description": "项目名（可选）"},
                    "project_id": {"type": "string", "description": "项目 ID（可选）"},
                    "compile_check": {"type": "boolean", "description": "是否执行编译检查（默认 true）"},
                },
                "required": ["ce_url"],
            },
        ),
        Tool(
            name="apply_compat_patches",
            description="手动应用 overleaf-sync-ce/socketIO 兼容补丁（通常无需手动执行）。",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    try:
        result = await _execute_tool(name, arguments or {})
        return [TextContent(type="text", text=result)]
    except Exception as exc:
        return [
            TextContent(
                type="text",
                text=_dump(
                    {
                        "ok": False,
                        "error": str(exc),
                        "hint": "可先调用 check_environment 查看依赖状态。",
                    }
                ),
            )
        ]


async def _execute_tool(name: str, arguments: Dict[str, Any]) -> str:
    if name == "check_environment":
        return _dump({"ok": True, "data": _collect_env_status()})

    if name == "ols_login":
        store_path = arguments.get("store_path")
        ce_url = arguments.get("ce_url")
        code, out, err = ols_login(store_path=store_path, ce_url=ce_url)
        return _dump(
            {
                "ok": code == 0,
                "exit_code": code,
                "stdout": out,
                "stderr": err,
                "note": "若无图形界面，建议先在有桌面的环境完成一次 login。",
            }
        )

    if name == "ols_list_projects":
        store_path = arguments.get("store_path")
        ce_url = arguments.get("ce_url")
        verbose = _as_bool(arguments.get("verbose"), default=False)
        code, out, err = ols_list(store_path=store_path, verbose=verbose, ce_url=ce_url)
        return _dump(
            {
                "ok": code == 0,
                "exit_code": code,
                "stdout": out,
                "stderr": err,
            }
        )

    if name == "ols_sync":
        workspace_path = arguments.get("workspace_path")
        mode = arguments.get("mode", "bidirectional")
        project_name = arguments.get("project_name")
        ce_url = arguments.get("ce_url")
        store_path = arguments.get("store_path")
        olignore = arguments.get("olignore")
        delete_policy = arguments.get("delete_policy")
        verbose = _as_bool(arguments.get("verbose"), default=False)

        code, out, err = ols_sync(
            workspace_path=workspace_path,
            mode=mode,
            project_name=project_name,
            ce_url=ce_url,
            store_path=store_path,
            olignore=olignore,
            delete_policy=delete_policy,
            verbose=verbose,
        )
        return _dump(
            {
                "ok": code == 0,
                "exit_code": code,
                "workspace_path": str(Path(workspace_path).resolve()) if workspace_path else None,
                "project_name": project_name,
                "ce_url": ce_url,
                "mode": mode,
                "stdout": out,
                "stderr": err,
            }
        )

    if name == "init_manuscript_from_template":
        template_name = arguments.get("template_name", "ocean-engineering-oa")
        target_dir = arguments.get("target_dir")
        if not target_dir:
            raise ValueError("target_dir 不能为空")
        data = init_template_project(
            template_name=template_name,
            target_dir=target_dir,
            title=arguments.get("title"),
            authors=arguments.get("authors"),
            corresponding_email=arguments.get("corresponding_email"),
            keywords=arguments.get("keywords"),
        )
        return _dump({"ok": True, "data": data})

    if name == "write_file":
        file_path = arguments.get("file_path")
        content = arguments.get("content")
        if not file_path:
            raise ValueError("file_path 不能为空")
        if content is None:
            raise ValueError("content 不能为空")
        p = Path(file_path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return _dump({"ok": True, "file_path": str(p), "bytes": len(content.encode("utf-8"))})

    if name == "compile_latex":
        project_dir = arguments.get("project_dir")
        if not project_dir:
            raise ValueError("project_dir 不能为空")
        main_tex = arguments.get("main_tex", "main.tex")
        if not command_exists("latexmk"):
            return _dump(
                {
                    "ok": False,
                    "error": "未检测到 latexmk",
                    "hint": "安装：sudo apt-get install -y texlive-latex-base texlive-latex-extra latexmk",
                }
            )

        wd = Path(project_dir).expanduser().resolve()
        tex = wd / main_tex
        if not tex.exists():
            raise ValueError("主文件不存在: %s" % str(tex))

        cmd = ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", main_tex]
        code, out, err = run_command(cmd, cwd=str(wd), timeout=1800)
        pdf_path = wd / (Path(main_tex).stem + ".pdf")
        return _dump(
            {
                "ok": code == 0 and pdf_path.exists(),
                "exit_code": code,
                "pdf_path": str(pdf_path) if pdf_path.exists() else None,
                "stdout_tail": out[-4000:],
                "stderr_tail": err[-4000:],
            }
        )

    if name == "package_project_zip":
        project_dir = arguments.get("project_dir")
        if not project_dir:
            raise ValueError("project_dir 不能为空")
        if not command_exists("zip"):
            raise ValueError("未检测到 zip 命令")

        wd = Path(project_dir).expanduser().resolve()
        if not wd.exists() or not wd.is_dir():
            raise ValueError("project_dir 不是有效目录: %s" % str(wd))

        output_zip = arguments.get("output_zip")
        if output_zip:
            out_zip = Path(output_zip).expanduser().resolve()
        else:
            out_zip = wd.parent / (wd.name + ".zip")
        out_zip.parent.mkdir(parents=True, exist_ok=True)

        # 在项目目录内部压缩，避免把绝对路径写入 zip
        if out_zip.exists():
            out_zip.unlink()
        code, out, err = run_command(
            ["zip", "-r", str(out_zip), "."],
            cwd=str(wd),
            timeout=1800,
        )
        return _dump(
            {
                "ok": code == 0 and out_zip.exists(),
                "exit_code": code,
                "zip_path": str(out_zip) if out_zip.exists() else None,
                "stdout": out[-2000:],
                "stderr": err[-2000:],
            }
        )

    if name == "upload_project_zip":
        ce_url = arguments.get("ce_url")
        zip_path = arguments.get("zip_path")
        if not ce_url:
            raise ValueError("ce_url 不能为空")
        if not zip_path:
            raise ValueError("zip_path 不能为空")

        store_path = arguments.get("store_path")
        if store_path:
            store = str(Path(store_path).expanduser().resolve())
        else:
            store = str((Path.home() / ".olauth").resolve())
        timeout = _as_int(arguments.get("timeout"), 300)
        health = _as_bool(arguments.get("health_check"), True)
        compile_check = _as_bool(arguments.get("compile_check"), True)

        data = upload_zip_as_new_project(
            ce_url=str(ce_url),
            store_path=store,
            zip_path=str(zip_path),
            timeout=timeout,
        )
        result: Dict[str, Any] = {"ok": True, "data": data}
        if health:
            result["health"] = health_check_project(
                ce_url=str(ce_url),
                store_path=store,
                project_id=str(data.get("project_id")),
                compile_check=compile_check,
            )
        return _dump(result)

    if name == "upload_project_dir":
        ce_url = arguments.get("ce_url")
        project_dir = arguments.get("project_dir")
        if not ce_url:
            raise ValueError("ce_url 不能为空")
        if not project_dir:
            raise ValueError("project_dir 不能为空")

        exclude_list = _as_globs(arguments.get("exclude_globs"))
        dry_run = _as_bool(arguments.get("dry_run"), False)
        target_project = (arguments.get("target_project") or "").strip() or None
        existing_strategy = str(arguments.get("existing_project_strategy", "merge")).strip().lower()
        if existing_strategy not in ("merge", "replace"):
            raise ValueError("existing_project_strategy 仅支持 merge/replace")
        health = _as_bool(arguments.get("health_check"), True)
        compile_check = _as_bool(arguments.get("compile_check"), True)
        verbose = _as_bool(arguments.get("verbose"), False)

        packed = package_project_for_upload(
            project_dir=str(project_dir),
            output_zip=arguments.get("output_zip"),
            exclude_globs=exclude_list,
        )

        store_path = arguments.get("store_path")
        if store_path:
            store = str(Path(store_path).expanduser().resolve())
        else:
            store = str((Path.home() / ".olauth").resolve())
        timeout = _as_int(arguments.get("timeout"), 300)

        # dry-run：只返回打包/执行计划，不触发远端操作
        if dry_run:
            return _dump(
                {
                    "ok": True,
                    "dry_run": True,
                    "pack": packed,
                    "plan": {
                        "mode": "sync_existing" if target_project else "upload_new_project",
                        "target_project": target_project,
                        "existing_project_strategy": existing_strategy if target_project else None,
                        "health_check": health,
                        "compile_check": compile_check,
                    },
                }
            )

        # 分支 A：未指定 target_project，创建新项目
        if not target_project:
            uploaded = upload_zip_as_new_project(
                ce_url=str(ce_url),
                store_path=store,
                zip_path=str(packed["zip_path"]),
                timeout=timeout,
            )
            result: Dict[str, Any] = {"ok": True, "pack": packed, "upload": uploaded}
            if health:
                result["health"] = health_check_project(
                    ce_url=str(ce_url),
                    store_path=store,
                    project_id=str(uploaded.get("project_id")),
                    compile_check=compile_check,
                )
            return _dump(result)

        # 分支 B：指定 target_project，同步到已有项目
        existing = find_project_by_name(
            ce_url=str(ce_url),
            store_path=store,
            project_name=target_project,
        )
        if existing is None:
            raise ValueError(f"目标项目不存在: {target_project}")

        # 将打包结果解压到临时目录，再走 ols --local-only 到目标项目。
        stage_root = Path(tempfile.mkdtemp(prefix="overleaf-ce-stage-")).resolve()
        stage_dir = stage_root / target_project
        try:
            stage_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(str(packed["zip_path"]), "r") as zf:
                zf.extractall(str(stage_dir))

            # 生成用于同步时过滤临时产物的 .olignore
            olignore_path = stage_dir / ".olignore"
            olignore_lines = [
                "*.aux",
                "*.bbl",
                "*.blg",
                "*.fdb_latexmk",
                "*.fls",
                "*.log",
                "*.out",
                "*.spl",
                "*.synctex.gz",
                "*.pdf",
                "*.zip",
            ]
            for g in exclude_list:
                if g not in olignore_lines:
                    olignore_lines.append(g)
            olignore_path.write_text("\n".join(olignore_lines) + "\n", encoding="utf-8")

            delete_policy = "d" if existing_strategy == "replace" else "i"
            code, out, err = ols_sync(
                workspace_path=str(stage_dir),
                project_name=target_project,
                ce_url=str(ce_url),
                mode="local-only",
                store_path=store,
                olignore=str(olignore_path),
                delete_policy=delete_policy,
                verbose=verbose,
            )

            result = {
                "ok": code == 0,
                "pack": packed,
                "sync": {
                    "exit_code": code,
                    "target_project": target_project,
                    "target_project_id": existing.get("id"),
                    "existing_project_strategy": existing_strategy,
                    "delete_policy": delete_policy,
                    "stage_dir": str(stage_dir),
                    "stdout": out,
                    "stderr": err,
                },
            }
            if health:
                result["health"] = health_check_project(
                    ce_url=str(ce_url),
                    store_path=store,
                    project_name=target_project,
                    compile_check=compile_check,
                )
            return _dump(result)
        finally:
            # 默认清理临时目录
            shutil.rmtree(stage_root, ignore_errors=True)

    if name == "health_check_project":
        ce_url = arguments.get("ce_url")
        if not ce_url:
            raise ValueError("ce_url 不能为空")
        store_path = arguments.get("store_path")
        if store_path:
            store = str(Path(store_path).expanduser().resolve())
        else:
            store = str((Path.home() / ".olauth").resolve())

        project_name = arguments.get("project_name")
        project_id = arguments.get("project_id")
        compile_check = _as_bool(arguments.get("compile_check"), True)

        data = health_check_project(
            ce_url=str(ce_url),
            store_path=store,
            project_name=str(project_name) if project_name else None,
            project_id=str(project_id) if project_id else None,
            compile_check=compile_check,
        )
        return _dump({"ok": bool(data.get("ok", False)), "data": data})

    if name == "apply_compat_patches":
        data = ensure_compat_patches()
        return _dump({"ok": bool(data.get("ok", False)), "data": data})

    raise ValueError("未知工具: %s" % name)


def main() -> None:
    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()
