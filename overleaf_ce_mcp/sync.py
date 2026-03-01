"""封装 overleaf-sync-ce 的命令调用。"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from .compat import ensure_compat_patches


def command_exists(cmd: str) -> bool:
    """判断命令是否存在。"""
    return resolve_command(cmd) is not None


def resolve_command(cmd: str) -> Optional[str]:
    """解析命令路径，优先使用当前 Python 环境对应的可执行文件。"""
    # 优先显式环境变量，便于手动覆盖。
    env_key = f"{cmd.upper()}_BIN"
    env_path = os.environ.get(env_key)
    if env_path and Path(env_path).is_file():
        return env_path

    found = shutil.which(cmd)
    if found:
        return found

    # 回退到当前 Python 可执行文件所在目录（优先保留 venv 真实路径，不解引用）。
    exe_parent = Path(sys.executable).parent
    sibling = exe_parent / cmd
    if sibling.is_file():
        return str(sibling)

    # 再回退到 sys.prefix/bin。
    prefix_bin = Path(sys.prefix) / "bin" / cmd
    if prefix_bin.is_file():
        return str(prefix_bin)
    return None


def run_command(
    cmd: List[str],
    cwd: Optional[str] = None,
    timeout: int = 600,
    env: Optional[dict] = None,
) -> Tuple[int, str, str]:
    """运行命令并返回 (返回码, 标准输出, 标准错误)。"""
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=env or os.environ.copy(),
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def run_ols(
    args: List[str],
    cwd: Optional[str] = None,
    timeout: int = 1200,
    extra_env: Optional[dict] = None,
) -> Tuple[int, str, str]:
    """运行 ols 命令。"""
    # 在调用 ols 前确保第三方兼容补丁已就位。
    ensure_compat_patches()

    ols_bin = resolve_command("ols")
    if not ols_bin:
        raise RuntimeError(
            "未检测到 `ols` 命令。请先安装：`pip install overleaf-sync-ce`"
        )
    env = os.environ.copy()
    path_parts = [str(Path(sys.executable).parent), str(Path(sys.prefix) / "bin"), env.get("PATH", "")]
    merged_parts: List[str] = []
    for part in path_parts:
        if part and part not in merged_parts:
            merged_parts.append(part)
    env["PATH"] = os.pathsep.join(merged_parts)
    if extra_env:
        env.update(extra_env)
    return run_command([ols_bin] + args, cwd=cwd, timeout=timeout, env=env)


def ols_login(store_path: Optional[str] = None, ce_url: Optional[str] = None) -> Tuple[int, str, str]:
    """执行 ols login。"""
    args = ["login"]
    if store_path:
        args += ["--path", store_path]
    if ce_url:
        args += ["--ce-url", ce_url]
    return run_ols(args)


def ols_list(
    store_path: Optional[str] = None,
    verbose: bool = False,
    ce_url: Optional[str] = None,
) -> Tuple[int, str, str]:
    """执行 ols list。"""
    args = ["list"]
    if store_path:
        args += ["--store-path", store_path]
    if ce_url:
        args += ["--ce-url", ce_url]
    if verbose:
        args += ["--verbose"]
    return run_ols(args)


def ols_sync(
    workspace_path: Optional[str] = None,
    mode: str = "bidirectional",
    project_name: Optional[str] = None,
    ce_url: Optional[str] = None,
    store_path: Optional[str] = None,
    olignore: Optional[str] = None,
    delete_policy: Optional[str] = None,
    verbose: bool = False,
) -> Tuple[int, str, str]:
    """执行 ols 同步。"""
    args: List[str] = []

    # 防止误把 workspace 根目录内容同步进单个项目：
    # 当传入 --name 且 workspace 下存在同名子目录时，自动收敛到该子目录。
    scoped_workspace = workspace_path
    if workspace_path and project_name:
        wp = Path(workspace_path).expanduser().resolve()
        candidate = wp / project_name
        if candidate.is_dir():
            scoped_workspace = str(candidate)

    if mode == "local-only":
        args.append("--local-only")
    elif mode == "remote-only":
        args.append("--remote-only")
    elif mode != "bidirectional":
        raise ValueError("mode 仅支持 bidirectional/local-only/remote-only")

    if project_name:
        args += ["--name", project_name]
    if scoped_workspace:
        args += ["--path", scoped_workspace]
    if ce_url:
        args += ["--ce-url", ce_url]
    if store_path:
        args += ["--store-path", store_path]
    if olignore:
        args += ["--olignore", olignore]
    if verbose:
        args += ["--verbose"]

    extra_env = {}
    if delete_policy:
        if delete_policy not in ("d", "r", "i"):
            raise ValueError("delete_policy 仅支持 d/r/i")
        extra_env["OLS_DELETE_POLICY"] = delete_policy

    # 未传 workspace_path 时，沿用 cwd 的项目目录推断策略。
    cwd = scoped_workspace if scoped_workspace else None
    return run_ols(args, cwd=cwd, extra_env=extra_env)
