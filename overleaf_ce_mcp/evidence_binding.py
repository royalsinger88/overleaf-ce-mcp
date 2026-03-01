"""手稿段落与证据账本绑定分析。"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def _read_claim_rows(claim_file: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if not claim_file.exists():
        return rows
    for raw in (claim_file.read_text(encoding="utf-8") or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        rows.append(
            {
                "claim_id": str(obj.get("claim_id") or "").strip(),
                "claim": str(obj.get("claim") or "").strip(),
                "source": str(obj.get("source") or "").strip(),
                "status": str(obj.get("status") or "").strip(),
            }
        )
    return rows


def _iter_tex_files(project_root: Path, include_sections: bool = True) -> List[Path]:
    files: List[Path] = []
    main_tex = project_root / "main.tex"
    if main_tex.exists():
        files.append(main_tex)
    if include_sections:
        sec = project_root / "sections"
        if sec.exists() and sec.is_dir():
            files.extend(sorted(sec.glob("*.tex")))
    return files


def _clean_tex_for_paragraphs(text: str) -> str:
    lines: List[str] = []
    for raw in text.splitlines():
        # 仅处理简单注释场景；保留结构稳定性。
        line = re.sub(r"(?<!\\)%.*$", "", raw).rstrip()
        if line:
            lines.append(line)
        else:
            lines.append("")
    return "\n".join(lines)


def _split_paragraphs(text: str) -> List[str]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    out: List[str] = []
    for b in blocks:
        s = b.strip()
        if not s:
            continue
        if s.startswith("\\section") or s.startswith("\\subsection"):
            continue
        if s.startswith("\\begin{") or s.startswith("\\end{"):
            continue
        if s.startswith("%"):
            continue
        out.append(s)
    return out


def _tokenize_claim(text: str) -> List[str]:
    toks: List[str] = []
    for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", text or ""):
        t = token.strip().lower()
        if len(t) >= 4:
            toks.append(t)
    return toks


def _paragraph_hit(paragraph: str, claims: List[Dict[str, str]], claim_tokens: Dict[str, List[str]]) -> Dict[str, Any]:
    low = paragraph.lower()
    # 1) 直接包含来源（doi/url/arxiv）优先命中。
    for c in claims:
        src = c.get("source") or ""
        if src and src.lower() in low:
            return {"covered": True, "rule": "source-literal", "claim_id": c.get("claim_id"), "source": src}
    # 2) claim_id 手工标注命中。
    for c in claims:
        cid = c.get("claim_id") or ""
        if cid and cid.lower() in low:
            return {"covered": True, "rule": "claim-id", "claim_id": cid, "source": c.get("source")}
    # 3) 关键词重叠命中（同一 claim 至少 2 个词）。
    for c in claims:
        cid = c.get("claim_id") or ""
        toks = claim_tokens.get(cid) or []
        if not toks:
            continue
        hits = 0
        for kw in toks:
            if kw in low:
                hits += 1
            if hits >= 2:
                return {
                    "covered": True,
                    "rule": "claim-keyword-overlap",
                    "claim_id": cid or None,
                    "source": c.get("source"),
                }
    return {"covered": False, "rule": "none", "claim_id": None, "source": None}


def _write_reports(project_root: Path, payload: Dict[str, Any]) -> Dict[str, str]:
    out_dir = project_root / "paper_state" / "outputs" / "evidence_binding"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    jp = out_dir / f"coverage_{ts}.json"
    mp = out_dir / f"coverage_{ts}.md"
    latest_json = out_dir / "latest.json"
    latest_md = out_dir / "latest.md"

    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    jp.write_text(raw, encoding="utf-8")
    latest_json.write_text(raw, encoding="utf-8")

    lines = [
        "# Manuscript Evidence Coverage",
        "",
        f"- 生成时间（UTC）：{payload.get('generated_at')}",
        f"- 段落总数：{payload.get('paragraph_total')}",
        f"- 覆盖段落：{payload.get('paragraph_covered')}",
        f"- 覆盖率：{payload.get('coverage_ratio')}",
        "",
        "## 文件覆盖率",
    ]
    file_rows = payload.get("files") if isinstance(payload.get("files"), list) else []
    if not file_rows:
        lines.append("- [无可分析手稿文件]")
    else:
        for fr in file_rows:
            lines.append(
                f"- {fr.get('file')} | paragraphs={fr.get('paragraph_count')} | "
                f"covered={fr.get('covered_count')} | ratio={fr.get('coverage_ratio')}"
            )
    lines.append("")
    lines.append("## 未覆盖段落（Top）")
    missing = payload.get("uncovered_top") if isinstance(payload.get("uncovered_top"), list) else []
    if not missing:
        lines.append("- [无]")
    else:
        for it in missing:
            lines.append(
                f"- {it.get('file')}#{it.get('paragraph_index')}: "
                f"{str(it.get('preview') or '').replace(chr(10), ' ')[:160]}"
            )
    md_text = "\n".join(lines).rstrip() + "\n"
    mp.write_text(md_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    return {
        "report_json": str(jp),
        "report_markdown": str(mp),
        "latest_json": str(latest_json),
        "latest_markdown": str(latest_md),
    }


def run_manuscript_evidence_binding(
    project_dir: str,
    include_sections: bool = True,
    max_uncovered: int = 30,
    write_report: bool = True,
) -> Dict[str, Any]:
    root = Path(project_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("project_dir 不是有效目录: %s" % str(root))

    claims = _read_claim_rows(root / "paper_state" / "memory" / "claim_evidence.jsonl")
    claim_tokens = {c.get("claim_id") or "": _tokenize_claim(c.get("claim") or "") for c in claims}

    paragraph_total = 0
    paragraph_covered = 0
    all_uncovered: List[Dict[str, Any]] = []
    files_summary: List[Dict[str, Any]] = []

    for tf in _iter_tex_files(root, include_sections=include_sections):
        text = _clean_tex_for_paragraphs(tf.read_text(encoding="utf-8"))
        paragraphs = _split_paragraphs(text)
        detail_rows: List[Dict[str, Any]] = []

        for idx, para in enumerate(paragraphs, start=1):
            paragraph_total += 1
            hit = _paragraph_hit(para, claims, claim_tokens)
            covered = bool(hit.get("covered"))
            if covered:
                paragraph_covered += 1
            row = {
                "paragraph_index": idx,
                "covered": covered,
                "rule": hit.get("rule"),
                "claim_id": hit.get("claim_id"),
                "source": hit.get("source"),
                "preview": para[:220],
            }
            detail_rows.append(row)
            if not covered:
                all_uncovered.append({"file": str(tf), **row})

        covered_count = sum(1 for x in detail_rows if x["covered"])
        files_summary.append(
            {
                "file": str(tf),
                "paragraph_count": len(detail_rows),
                "covered_count": covered_count,
                "coverage_ratio": round((covered_count / len(detail_rows)), 4) if detail_rows else 0.0,
                "paragraphs": detail_rows[:120],
            }
        )

    ratio = round((paragraph_covered / paragraph_total), 4) if paragraph_total > 0 else 0.0
    payload: Dict[str, Any] = {
        "ok": True,
        "project_dir": str(root),
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "claims_count": len(claims),
        "paragraph_total": paragraph_total,
        "paragraph_covered": paragraph_covered,
        "coverage_ratio": ratio,
        "files": files_summary,
        "uncovered_top": all_uncovered[: max(1, int(max_uncovered))],
    }
    if write_report:
        payload["paths"] = _write_reports(root, payload)
    return payload

