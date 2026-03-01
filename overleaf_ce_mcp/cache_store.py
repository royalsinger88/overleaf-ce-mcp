"""轻量文件缓存（按参数哈希键）。"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional


def build_cache_key(payload: Dict[str, Any]) -> str:
    """基于稳定 JSON 序列化计算缓存键。"""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_path(project_root: Path, namespace: str, key: str) -> Path:
    """返回缓存文件路径，并确保目录存在。"""
    safe_ns = namespace.strip().replace("\\", "/").strip("/")
    if not safe_ns:
        safe_ns = "default"
    d = project_root / "paper_state" / "cache" / safe_ns
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.json"


def load_cache(path: Path, ttl_hours: int = 24) -> Optional[Dict[str, Any]]:
    """读取缓存；过期或格式异常返回 None。"""
    if not path.exists() or not path.is_file():
        return None
    age_seconds = _dt.datetime.now(_dt.timezone.utc).timestamp() - path.stat().st_mtime
    if age_seconds > max(1, int(ttl_hours)) * 3600:
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    if not isinstance(obj.get("data"), dict):
        return None
    return {
        "key": obj.get("key"),
        "cached_at": obj.get("cached_at"),
        "data": obj.get("data"),
        "meta": obj.get("meta") if isinstance(obj.get("meta"), dict) else {},
    }


def save_cache(path: Path, key: str, data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None) -> None:
    """写入缓存。"""
    payload = {
        "key": key,
        "cached_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "data": data,
        "meta": meta or {},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

