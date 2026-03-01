"""paper_state 输入规范校验器（paper_doctor）。"""

from __future__ import annotations

import csv
import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def _read_text(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _yaml_scalar(path: Path, key: str) -> Optional[str]:
    text = _read_text(path) or ""
    if not text.strip():
        return None
    m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.*?)\s*$", text, flags=re.MULTILINE)
    if not m:
        return None
    raw = m.group(1).split("#", 1)[0].strip()
    if not raw:
        return None
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        raw = raw[1:-1].strip()
    if raw in ("null", "None", "none", "[]", "{}", '""'):
        return None
    return raw


def _issue(
    issue_id: str,
    severity: str,
    file_path: str,
    message: str,
    suggestion: str,
) -> Dict[str, str]:
    return {
        "id": issue_id,
        "severity": severity,
        "file": file_path,
        "message": message,
        "suggestion": suggestion,
    }


def _write_report(project_root: Path, report: Dict[str, Any]) -> Dict[str, str]:
    out_dir = project_root / "paper_state" / "outputs" / "paper_doctor"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"doctor_{ts}.json"
    md_path = out_dir / f"doctor_{ts}.md"
    latest_json = out_dir / "latest.json"
    latest_md = out_dir / "latest.md"

    json_text = json.dumps(report, ensure_ascii=False, indent=2)
    json_path.write_text(json_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")

    issues = report.get("issues") or []
    lines = [
        "# Paper Doctor Report",
        "",
        f"- 检查时间（UTC）：{report.get('checked_at')}",
        f"- 总问题数：{len(issues)}",
        f"- HIGH/MEDIUM/LOW：{report.get('summary', {}).get('high', 0)}/"
        f"{report.get('summary', {}).get('medium', 0)}/{report.get('summary', {}).get('low', 0)}",
        "",
        "## 问题清单",
    ]
    if not issues:
        lines.append("- [无问题]")
    else:
        for it in issues:
            lines.append(
                f"- [{it.get('severity')}] {it.get('id')} | {it.get('file')} | "
                f"{it.get('message')} | 建议：{it.get('suggestion')}"
            )
    md_text = "\n".join(lines).rstrip() + "\n"
    md_path.write_text(md_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    return {
        "report_json": str(json_path),
        "report_markdown": str(md_path),
        "latest_json": str(latest_json),
        "latest_markdown": str(latest_md),
    }


def run_paper_doctor(project_dir: str, write_report: bool = True) -> Dict[str, Any]:
    root = Path(project_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("project_dir 不是有效目录: %s" % str(root))

    inputs = root / "paper_state" / "inputs"
    literature = inputs / "literature"
    memory = root / "paper_state" / "memory"
    issues: List[Dict[str, str]] = []

    # 1) project.yaml
    project_yaml = inputs / "project.yaml"
    if not project_yaml.exists():
        issues.append(
            _issue(
                "missing_project_yaml",
                "high",
                str(project_yaml),
                "缺少 project.yaml",
                "执行 init_paper_state_workspace 初始化基础输入。",
            )
        )
    else:
        title = _yaml_scalar(project_yaml, "title")
        if not title:
            issues.append(
                _issue(
                    "missing_title",
                    "high",
                    str(project_yaml),
                    "project.title 缺失或为空",
                    "在 project.yaml 中补充 title。",
                )
            )

    # 2) writing_brief
    brief = inputs / "writing_brief.md"
    brief_text = _read_text(brief)
    if not brief_text:
        issues.append(
            _issue(
                "missing_writing_brief",
                "high",
                str(brief),
                "缺少 writing_brief.md 或内容为空",
                "补充研究问题、创新点和关键实验数据。",
            )
        )
    else:
        key_words = ["研究问题", "预期创新点", "当前证据"]
        for kw in key_words:
            if kw not in brief_text:
                issues.append(
                    _issue(
                        "brief_section_missing",
                        "medium",
                        str(brief),
                        f"缺少章节：{kw}",
                        "按模板补齐写作素材，提升自动扫描质量。",
                    )
                )

    # 3) submission_target
    sub_yaml = inputs / "submission_target.yaml"
    if not sub_yaml.exists():
        issues.append(
            _issue(
                "missing_submission_target",
                "medium",
                str(sub_yaml),
                "缺少 submission_target.yaml",
                "补充目标期刊与投稿偏好。",
            )
        )
    else:
        pj = _yaml_scalar(sub_yaml, "primary_target_journal")
        if not pj:
            issues.append(
                _issue(
                    "missing_primary_journal",
                    "medium",
                    str(sub_yaml),
                    "primary_target_journal 缺失",
                    "至少填写一个主投期刊，例如 Ocean Engineering。",
                )
            )

    # 4) reading_queue.csv
    rq = literature / "reading_queue.csv"
    expected_cols = ["title", "source", "url_or_doi", "priority", "status", "notes"]
    if not rq.exists():
        issues.append(
            _issue(
                "missing_reading_queue",
                "high",
                str(rq),
                "缺少 reading_queue.csv",
                "创建文件并写入表头。",
            )
        )
    else:
        try:
            with rq.open("r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                header = next(reader, [])
            miss = [x for x in expected_cols if x not in header]
            if miss:
                issues.append(
                    _issue(
                        "reading_queue_bad_header",
                        "high",
                        str(rq),
                        f"reading_queue.csv 表头缺失字段: {', '.join(miss)}",
                        f"修正为至少包含: {', '.join(expected_cols)}",
                    )
                )
        except Exception:
            issues.append(
                _issue(
                    "reading_queue_parse_error",
                    "high",
                    str(rq),
                    "reading_queue.csv 无法解析",
                    "确保为 UTF-8 编码且 CSV 格式正确。",
                )
            )

    # 5) claim_evidence.jsonl
    claim_file = memory / "claim_evidence.jsonl"
    required_claim_keys = ["claim_id", "claim", "source_type", "source", "confidence", "status"]
    if not claim_file.exists():
        issues.append(
            _issue(
                "missing_claim_evidence",
                "medium",
                str(claim_file),
                "缺少 claim_evidence.jsonl",
                "创建账本文件用于结论-证据可追溯。",
            )
        )
    else:
        bad_count = 0
        checked = 0
        for raw in (claim_file.read_text(encoding="utf-8") or "").splitlines():
            line = raw.strip()
            if not line:
                continue
            checked += 1
            try:
                obj = json.loads(line)
            except Exception:
                bad_count += 1
                continue
            if not isinstance(obj, dict):
                bad_count += 1
                continue
            if any(k not in obj for k in required_claim_keys):
                bad_count += 1
        if checked > 0 and bad_count > 0:
            issues.append(
                _issue(
                    "claim_evidence_invalid_rows",
                    "high",
                    str(claim_file),
                    f"claim_evidence.jsonl 有 {bad_count}/{checked} 行格式不合规",
                    "补齐必需字段并确保每行是合法 JSON。",
                )
            )

    # 6) constraints / loop
    constraints = inputs / "constraints.yaml"
    if not constraints.exists():
        issues.append(
            _issue(
                "missing_constraints_yaml",
                "low",
                str(constraints),
                "缺少 constraints.yaml",
                "建议补充页数、预算、禁用主张等约束。",
            )
        )
    loop = inputs / "loop.yaml"
    if not loop.exists():
        issues.append(
            _issue(
                "missing_loop_yaml",
                "medium",
                str(loop),
                "缺少 loop.yaml",
                "建议配置循环参数，便于稳定迭代。",
            )
        )

    high = sum(1 for x in issues if x["severity"] == "high")
    medium = sum(1 for x in issues if x["severity"] == "medium")
    low = sum(1 for x in issues if x["severity"] == "low")
    score = max(0.0, round(1.0 - ((high * 0.2) + (medium * 0.08) + (low * 0.03)), 4))

    report: Dict[str, Any] = {
        "ok": high == 0,
        "project_dir": str(root),
        "checked_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "score": score,
        "summary": {"high": high, "medium": medium, "low": low},
        "issues": issues,
    }
    if write_report:
        report["paths"] = _write_report(root, report)
    return report

