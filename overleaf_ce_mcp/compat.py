"""第三方依赖兼容补丁管理。"""

import shutil
import sys
from pathlib import Path
from typing import Dict, List


def _venv_site_packages() -> Path:
    """根据当前解释器解析 site-packages 目录。"""
    # 在 venv 下优先使用 sys.prefix，避免 symlink resolve 到 base python。
    prefix = Path(sys.prefix)
    site = prefix / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    return site


def _patch_pairs() -> List[tuple[Path, Path]]:
    """返回 (源补丁文件, 目标文件) 映射。"""
    base = Path(__file__).resolve().parent / "vendor_patches"
    site = _venv_site_packages()
    return [
        (base / "olsync" / "olsync.py", site / "olsync" / "olsync.py"),
        (base / "olsync" / "olclient.py", site / "olsync" / "olclient.py"),
        (base / "olsync" / "olbrowserlogin.py", site / "olsync" / "olbrowserlogin.py"),
        (base / "socketIO_client" / "transports.py", site / "socketIO_client" / "transports.py"),
    ]


def ensure_compat_patches() -> Dict[str, object]:
    """
    应用兼容补丁（幂等）。

    返回结构：
    - ok: 是否全部成功
    - applied: 实际替换的目标文件
    - skipped: 已一致无需替换的目标文件
    - missing: 缺失源/目标文件
    """
    applied: List[str] = []
    skipped: List[str] = []
    missing: List[str] = []

    for src, dst in _patch_pairs():
        if not src.exists() or not dst.exists():
            missing.append(f"{src} -> {dst}")
            continue
        src_text = src.read_text(encoding="utf-8")
        dst_text = dst.read_text(encoding="utf-8")
        if src_text == dst_text:
            skipped.append(str(dst))
            continue
        shutil.copy2(src, dst)
        applied.append(str(dst))

    return {
        "ok": len(missing) == 0,
        "applied": applied,
        "skipped": skipped,
        "missing": missing,
    }
