"""模板初始化与渲染。"""

import datetime as _dt
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional


PKG_ROOT = Path(__file__).resolve().parent.parent


def _resolve_template_root() -> Path:
    """解析模板目录，兼容源码运行与安装后运行。"""
    env_root = os.environ.get("OVERLEAF_CE_MCP_TEMPLATE_ROOT")
    candidates = []
    if env_root:
        candidates.append(Path(env_root).expanduser().resolve())
    candidates.append((PKG_ROOT / "templates").resolve())
    candidates.append((Path.cwd() / "templates").resolve())
    candidates.append(Path("/root/overleaf-ce-mcp/templates").resolve())

    for c in candidates:
        if c.exists() and c.is_dir():
            return c
    return candidates[0]


def list_templates() -> List[str]:
    """列出可用模板。"""
    template_root = _resolve_template_root()
    if not template_root.exists():
        return []
    out: List[str] = []
    for p in template_root.iterdir():
        if p.is_dir():
            out.append(p.name)
    return sorted(out)


def _replace_placeholders(text: str, variables: Dict[str, str]) -> str:
    for k, v in variables.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def init_template_project(
    template_name: str,
    target_dir: str,
    title: Optional[str] = None,
    authors: Optional[str] = None,
    corresponding_email: Optional[str] = None,
    keywords: Optional[str] = None,
) -> Dict[str, object]:
    """用模板初始化项目目录并替换占位符。"""
    template_root = _resolve_template_root()
    src = template_root / template_name
    if not src.exists() or not src.is_dir():
        raise ValueError("模板不存在: %s" % template_name)

    dst = Path(target_dir).expanduser().resolve()
    dst.mkdir(parents=True, exist_ok=True)
    if any(dst.iterdir()):
        raise ValueError("目标目录非空，请使用空目录: %s" % str(dst))

    # 复制模板目录
    shutil.copytree(src, dst, dirs_exist_ok=True)

    vars_map = {
        "TITLE": title or "A Data-Driven Study for Ocean Engineering Applications",
        "AUTHORS": authors or "First Author, Second Author",
        "CORRESPONDING_EMAIL": corresponding_email or "author@example.com",
        "KEYWORDS": keywords or "Ocean engineering, CFD, Reliability, Optimization",
        "DATE": _dt.date.today().isoformat(),
    }

    rendered: List[str] = []
    for root, _, files in os.walk(str(dst)):
        for fn in files:
            if not fn.endswith(".tex"):
                continue
            fp = Path(root) / fn
            old = fp.read_text(encoding="utf-8")
            new = _replace_placeholders(old, vars_map)
            fp.write_text(new, encoding="utf-8")
            rendered.append(str(fp.relative_to(dst)))

    created: List[str] = []
    for root, _, files in os.walk(str(dst)):
        for fn in files:
            p = Path(root) / fn
            created.append(str(p.relative_to(dst)))

    return {
        "target_dir": str(dst),
        "template": template_name,
        "rendered_tex_files": sorted(rendered),
        "created_files": sorted(created),
    }
