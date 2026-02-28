"""Overleaf CE 通用上传工具。"""

import fnmatch
import os
import pickle
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup


DEFAULT_EXCLUDE_GLOBS: List[str] = [
    ".git/*",
    ".git/**",
    "__pycache__/*",
    "__pycache__/**",
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


def _normalize_ce_url(ce_url: str) -> str:
    if not ce_url:
        raise ValueError("ce_url 不能为空")
    return ce_url.rstrip("/")


def _load_store(store_path: str) -> Dict[str, object]:
    p = Path(store_path).expanduser().resolve()
    if not p.exists():
        raise ValueError(f"认证文件不存在: {p}")
    with p.open("rb") as f:
        data = pickle.load(f)
    if not isinstance(data, dict) or "cookie" not in data:
        raise ValueError(f"认证文件格式不正确: {p}")
    return data


def _ensure_cookie_aliases(cookie: Dict[str, str]) -> Dict[str, str]:
    out = dict(cookie)
    sid = out.get("overleaf.sid") or out.get("sharelatex.sid")
    if sid:
        out.setdefault("overleaf.sid", sid)
        out.setdefault("sharelatex.sid", sid)
    return out


def _refresh_csrf(base_url: str, cookies: Dict[str, str], timeout: int = 30) -> str:
    page = requests.get(f"{base_url}/project", cookies=cookies, timeout=timeout)
    page.raise_for_status()
    soup = BeautifulSoup(page.text, "html.parser")
    meta = soup.find("meta", {"name": "ol-csrfToken"})
    if meta is None:
        raise RuntimeError("未找到 ol-csrfToken，可能未登录或 CE 页面结构变化")
    csrf = (meta.get("content") or "").strip()
    if not csrf:
        raise RuntimeError("ol-csrfToken 为空")
    return csrf


def _load_project_blob(base_url: str, cookies: Dict[str, str], timeout: int = 30) -> Dict[str, object]:
    page = requests.get(f"{base_url}/project", cookies=cookies, timeout=timeout)
    page.raise_for_status()
    soup = BeautifulSoup(page.text, "html.parser")
    meta = soup.find("meta", {"name": "ol-projects"})
    if meta is None:
        meta = soup.find("meta", {"name": "ol-prefetchedProjectsBlob"})
    if meta is None:
        text = soup.get_text(" ", strip=True)
        if "Log in" in text or "Sign up" in text:
            raise RuntimeError("当前认证无效，访问 /project 被重定向到登录页")
        raise RuntimeError("未找到项目列表元数据（ol-projects/ol-prefetchedProjectsBlob）")
    content = meta.get("content") or ""
    if not content:
        raise RuntimeError("项目元数据为空")
    import json

    data = json.loads(content)
    if not isinstance(data, dict) or "projects" not in data:
        raise RuntimeError("项目元数据格式不符合预期")
    return data


def list_projects(
    ce_url: str,
    store_path: str,
    timeout: int = 30,
) -> List[Dict[str, object]]:
    base_url = _normalize_ce_url(ce_url)
    store = _load_store(store_path)
    cookie_raw = store.get("cookie")
    if not isinstance(cookie_raw, dict):
        raise ValueError("认证文件 cookie 字段无效")
    cookies = _ensure_cookie_aliases(cookie_raw)
    blob = _load_project_blob(base_url, cookies, timeout=timeout)
    projects = blob.get("projects", [])
    if not isinstance(projects, list):
        raise RuntimeError("projects 字段类型异常")
    out = []
    for p in projects:
        if not isinstance(p, dict):
            continue
        if p.get("archived") or p.get("trashed"):
            continue
        out.append(p)
    return out


def find_project_by_name(
    ce_url: str,
    store_path: str,
    project_name: str,
    timeout: int = 30,
) -> Optional[Dict[str, object]]:
    for p in list_projects(ce_url=ce_url, store_path=store_path, timeout=timeout):
        if str(p.get("name", "")).strip() == project_name.strip():
            return p
    return None


def compile_project(
    ce_url: str,
    store_path: str,
    project_id: str,
    timeout: int = 180,
) -> Dict[str, object]:
    base_url = _normalize_ce_url(ce_url)
    store = _load_store(store_path)
    cookie_raw = store.get("cookie")
    if not isinstance(cookie_raw, dict):
        raise ValueError("认证文件 cookie 字段无效")
    cookies = _ensure_cookie_aliases(cookie_raw)

    csrf = _refresh_csrf(base_url, cookies, timeout=30)
    headers = {"X-Csrf-Token": csrf}
    payload = {"check": "silent", "draft": False, "incrementalCompilesEnabled": False}
    resp = requests.post(
        f"{base_url}/project/{project_id}/compile",
        cookies=cookies,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    text = resp.text or ""
    try:
        data = resp.json()
    except Exception:
        data = {}

    output_files = data.get("outputFiles", []) if isinstance(data, dict) else []
    pdf_info = None
    if isinstance(output_files, list):
        for item in output_files:
            if isinstance(item, dict) and str(item.get("path", "")).endswith(".pdf"):
                pdf_info = item
                break

    pdf_url = None
    if isinstance(pdf_info, dict):
        raw_url = pdf_info.get("url")
        if isinstance(raw_url, str):
            if raw_url.startswith("http://") or raw_url.startswith("https://"):
                pdf_url = raw_url
            else:
                pdf_url = f"{base_url}{raw_url}"

    compile_status = data.get("status") if isinstance(data, dict) else None
    compile_ok = resp.status_code == 200 and isinstance(data, dict) and compile_status == "success"
    return {
        "ok": compile_ok,
        "status_code": resp.status_code,
        "compile_status": compile_status,
        "output_files_count": len(output_files) if isinstance(output_files, list) else 0,
        "has_pdf": pdf_info is not None,
        "pdf_url": pdf_url,
        "response_excerpt": text[:600].replace("\n", " "),
        "checked_at": datetime.utcnow().isoformat() + "Z",
    }


def health_check_project(
    ce_url: str,
    store_path: str,
    project_name: Optional[str] = None,
    project_id: Optional[str] = None,
    compile_check: bool = True,
) -> Dict[str, object]:
    if not project_id and not project_name:
        raise ValueError("project_id 和 project_name 至少提供一个")

    resolved = None
    if project_name:
        resolved = find_project_by_name(ce_url=ce_url, store_path=store_path, project_name=project_name)
        if resolved is None and not project_id:
            return {"ok": False, "error": f"未找到项目: {project_name}"}

    pid = project_id or (resolved.get("id") if isinstance(resolved, dict) else None)
    if not pid:
        return {"ok": False, "error": "无法解析项目 ID"}

    result = {
        "ok": True,
        "project_id": pid,
        "project_name": resolved.get("name") if isinstance(resolved, dict) else project_name,
    }
    if compile_check:
        result["compile"] = compile_project(ce_url=ce_url, store_path=store_path, project_id=str(pid))
        result["ok"] = result["ok"] and bool(result["compile"].get("ok"))
    return result


def _match_any(path_posix: str, patterns: Iterable[str]) -> bool:
    name = path_posix.rsplit("/", 1)[-1]
    for pat in patterns:
        if fnmatch.fnmatch(path_posix, pat) or fnmatch.fnmatch(name, pat):
            return True
    return False


def package_project_for_upload(
    project_dir: str,
    output_zip: Optional[str] = None,
    exclude_globs: Optional[List[str]] = None,
) -> Dict[str, object]:
    root = Path(project_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"project_dir 不是有效目录: {root}")

    patterns = list(DEFAULT_EXCLUDE_GLOBS)
    if exclude_globs:
        patterns.extend([p.strip() for p in exclude_globs if p and p.strip()])

    if output_zip:
        out_zip = Path(output_zip).expanduser().resolve()
    else:
        out_zip = root.parent / f"{root.name}-upload.zip"
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    if out_zip.exists():
        out_zip.unlink()

    included: List[str] = []
    skipped: List[str] = []

    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fp in sorted(root.rglob("*")):
            if fp.is_dir():
                continue
            rel = fp.relative_to(root).as_posix()
            if _match_any(rel, patterns):
                skipped.append(rel)
                continue
            zf.write(fp, arcname=rel)
            included.append(rel)

    if not included:
        raise RuntimeError("打包后没有可上传文件，请检查排除规则")

    return {
        "zip_path": str(out_zip),
        "project_dir": str(root),
        "included_count": len(included),
        "skipped_count": len(skipped),
        "included_sample": included[:20],
        "skipped_sample": skipped[:20],
    }


def upload_zip_as_new_project(
    ce_url: str,
    store_path: str,
    zip_path: str,
    timeout: int = 300,
) -> Dict[str, object]:
    base_url = _normalize_ce_url(ce_url)
    store = _load_store(store_path)
    cookie_raw = store.get("cookie")
    if not isinstance(cookie_raw, dict):
        raise ValueError("认证文件 cookie 字段无效")
    cookies = _ensure_cookie_aliases(cookie_raw)

    zp = Path(zip_path).expanduser().resolve()
    if not zp.exists() or not zp.is_file():
        raise ValueError(f"zip 文件不存在: {zp}")

    csrf = _refresh_csrf(base_url, cookies, timeout=30)
    headers = {
        "X-CSRF-TOKEN": csrf,
        "X-Csrf-Token": csrf,
        "X-Requested-With": "XMLHttpRequest",
    }
    # 兼容 CE 的上传处理逻辑：除 qqfile 外，补充 name/type 元数据。
    form = {
        "name": zp.name,
        "type": "application/zip",
        "relativePath": "",
    }

    with zp.open("rb") as f:
        files = {"qqfile": (zp.name, f, "application/zip")}
        resp = requests.post(
            f"{base_url}/project/new/upload",
            cookies=cookies,
            headers=headers,
            data=form,
            files=files,
            timeout=timeout,
        )

    text = resp.text or ""
    try:
        data = resp.json()
    except Exception:
        data = None

    ok = resp.status_code == 200 and isinstance(data, dict) and data.get("success") is True
    if not ok:
        raise RuntimeError(
            "上传失败: status=%s body=%s"
            % (resp.status_code, text[:500].replace("\n", " "))
        )

    project_id = data.get("project_id")
    return {
        "ok": True,
        "status_code": resp.status_code,
        "project_id": project_id,
        "project_url": f"{base_url}/project/{project_id}" if project_id else None,
        "zip_path": str(zp),
    }
