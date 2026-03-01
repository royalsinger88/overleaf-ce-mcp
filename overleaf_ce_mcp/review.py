"""论文写作复盘自动化（日复盘/周总结）。"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _parse_date(raw: Optional[str], default: _dt.date) -> _dt.date:
    if raw is None or not str(raw).strip():
        return default
    try:
        return _dt.date.fromisoformat(str(raw).strip())
    except Exception as exc:
        raise ValueError("日期格式错误，应为 YYYY-MM-DD") from exc


def _parse_datetime(raw: Any) -> Optional[_dt.datetime]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return _dt.datetime.fromisoformat(text)
    except Exception:
        return None


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _load_round_results(project_root: Path) -> List[Dict[str, Any]]:
    root = project_root / "paper_state" / "outputs" / "optimization_loop"
    if not root.exists() or not root.is_dir():
        return []
    out: List[Dict[str, Any]] = []
    for fp in sorted(root.glob("round_*/round_result.json")):
        data = _read_json(fp)
        if not data:
            continue
        ts = _parse_datetime(data.get("generated_at"))
        if ts is None:
            ts = _dt.datetime.fromtimestamp(fp.stat().st_mtime, tz=_dt.timezone.utc)
        row = dict(data)
        row["_generated_dt"] = ts
        row["_path"] = str(fp)
        out.append(row)
    return out


def _load_claim_evidence(project_root: Path) -> List[Dict[str, Any]]:
    fp = project_root / "paper_state" / "memory" / "claim_evidence.jsonl"
    if not fp.exists() or not fp.is_file():
        return []
    out: List[Dict[str, Any]] = []
    for raw in fp.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        ts = _parse_datetime(obj.get("recorded_at"))
        row = dict(obj)
        row["_recorded_dt"] = ts
        out.append(row)
    return out


def _week_range(anchor: _dt.date) -> Dict[str, _dt.date]:
    start = anchor - _dt.timedelta(days=anchor.weekday())
    end = start + _dt.timedelta(days=6)
    return {"start": start, "end": end}


def _safe_lines(items: List[str], empty_text: str = "- [无]") -> str:
    if not items:
        return empty_text
    return "\n".join([f"- {x}" for x in items])


def _update_review_state(
    project_root: Path,
    section: str,
    payload: Dict[str, Any],
) -> str:
    memory_dir = project_root / "paper_state" / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    fp = memory_dir / "review_state.json"
    state: Dict[str, Any] = {}
    if fp.exists() and fp.is_file():
        try:
            old = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(old, dict):
                state = old
        except Exception:
            state = {}
    state["updated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    state[section] = payload
    fp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(fp)


def generate_daily_review(
    project_dir: str,
    day: Optional[str] = None,
    overwrite: bool = True,
    write_state: bool = True,
) -> Dict[str, Any]:
    root = Path(project_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("project_dir 不是有效目录: %s" % str(root))

    target = _parse_date(day, default=_dt.date.today())
    rounds = _load_round_results(root)
    claims = _load_claim_evidence(root)

    day_rounds = [r for r in rounds if r["_generated_dt"].date() == target]
    day_claims = [c for c in claims if c["_recorded_dt"] and c["_recorded_dt"].date() == target]

    evidence_items: List[str] = []
    for c in day_claims[:8]:
        claim = str(c.get("claim") or "").strip() or "[未命名主张]"
        source = str(c.get("source") or "").strip() or "[无来源]"
        status = str(c.get("status") or "candidate").strip()
        evidence_items.append(f"{claim} ({status}) <- {source}")

    rejected_items: List[str] = []
    for c in day_claims:
        status = str(c.get("status") or "").strip().lower()
        if status in ("rejected", "invalid", "discarded"):
            rejected_items.append(str(c.get("claim") or "[未命名主张]").strip())

    failed_items: List[str] = []
    for r in day_rounds:
        improve = float(r.get("improvement") or 0.0)
        new_evidence = int(r.get("new_evidence_count") or 0)
        if improve < 0 or new_evidence == 0:
            failed_items.append(
                f"Round {r.get('round_index')}: improvement={improve}, new_evidence={new_evidence}"
            )

    next_actions: List[str] = []
    if day_rounds:
        latest = day_rounds[-1]
        actions = latest.get("next_actions")
        if isinstance(actions, list):
            for x in actions[:5]:
                s = str(x).strip()
                if s:
                    next_actions.append(s)

    best_score = max([float(r.get("score") or 0.0) for r in day_rounds], default=0.0)
    total_new_evidence = sum([int(r.get("new_evidence_count") or 0) for r in day_rounds])

    md = (
        f"# Daily Review - {target.isoformat()}\n\n"
        f"## 新增证据\n{_safe_lines(evidence_items)}\n\n"
        f"## 被否决主张\n{_safe_lines(rejected_items)}\n\n"
        f"## 失败实验\n{_safe_lines(failed_items)}\n\n"
        f"## 明日最小闭环动作\n{_safe_lines(next_actions)}\n\n"
        "## 自动汇总指标\n"
        f"- 当日优化轮次：{len(day_rounds)}\n"
        f"- 当日新增证据总数：{total_new_evidence}\n"
        f"- 当日最高评分：{round(best_score, 4)}\n"
    )

    out_file = root / "paper_state" / "review" / "daily" / f"{target.isoformat()}.md"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    if out_file.exists() and not overwrite:
        raise ValueError("目标日报已存在，若需覆盖请传 overwrite=true")
    out_file.write_text(md, encoding="utf-8")

    state_path = None
    payload = {
        "date": target.isoformat(),
        "path": str(out_file),
        "round_count": len(day_rounds),
        "new_evidence_total": total_new_evidence,
        "best_score": round(best_score, 4),
    }
    if write_state:
        state_path = _update_review_state(root, "daily", payload)

    return {
        "ok": True,
        "date": target.isoformat(),
        "path": str(out_file),
        "round_count": len(day_rounds),
        "new_evidence_total": total_new_evidence,
        "best_score": round(best_score, 4),
        "state_path": state_path,
    }


def generate_weekly_summary(
    project_dir: str,
    anchor_day: Optional[str] = None,
    overwrite: bool = True,
    write_state: bool = True,
) -> Dict[str, Any]:
    root = Path(project_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("project_dir 不是有效目录: %s" % str(root))

    anchor = _parse_date(anchor_day, default=_dt.date.today())
    wr = _week_range(anchor)
    start = wr["start"]
    end = wr["end"]
    iso_year, iso_week, _ = anchor.isocalendar()
    week_tag = f"{iso_year}-W{iso_week:02d}"

    rounds = _load_round_results(root)
    claims = _load_claim_evidence(root)
    week_rounds = [r for r in rounds if start <= r["_generated_dt"].date() <= end]
    week_claims = [c for c in claims if c["_recorded_dt"] and start <= c["_recorded_dt"].date() <= end]

    evidence_items: List[str] = []
    for c in week_claims[:12]:
        claim = str(c.get("claim") or "").strip() or "[未命名主张]"
        source = str(c.get("source") or "").strip() or "[无来源]"
        evidence_items.append(f"{claim} <- {source}")

    rejected_items: List[str] = []
    for c in week_claims:
        status = str(c.get("status") or "").strip().lower()
        if status in ("rejected", "invalid", "discarded"):
            rejected_items.append(str(c.get("claim") or "[未命名主张]").strip())

    failed_items: List[str] = []
    for r in week_rounds:
        improve = float(r.get("improvement") or 0.0)
        new_evidence = int(r.get("new_evidence_count") or 0)
        if improve < 0 or new_evidence == 0:
            failed_items.append(
                f"Round {r.get('round_index')}: improvement={improve}, new_evidence={new_evidence}"
            )

    weekly_actions: List[str] = []
    if week_rounds:
        latest = week_rounds[-1]
        actions = latest.get("next_actions")
        if isinstance(actions, list):
            for x in actions[:3]:
                s = str(x).strip()
                if s:
                    weekly_actions.append(s)

    round_count = len(week_rounds)
    total_new_evidence = sum([int(r.get("new_evidence_count") or 0) for r in week_rounds])
    best_score = max([float(r.get("score") or 0.0) for r in week_rounds], default=0.0)

    daily_dir = root / "paper_state" / "review" / "daily"
    daily_used: List[str] = []
    if daily_dir.exists() and daily_dir.is_dir():
        for fp in sorted(daily_dir.glob("*.md")):
            try:
                d = _dt.date.fromisoformat(fp.stem)
            except Exception:
                continue
            if start <= d <= end:
                daily_used.append(str(fp))

    md = (
        f"# Weekly Summary - {week_tag}\n\n"
        f"## 本周新增证据\n{_safe_lines(evidence_items)}\n\n"
        f"## 本周被否决主张\n{_safe_lines(rejected_items)}\n\n"
        f"## 本周失败实验\n{_safe_lines(failed_items)}\n\n"
        f"## 下周最小闭环目标\n{_safe_lines(weekly_actions)}\n\n"
        "## 自动汇总指标\n"
        f"- 周范围：{start.isoformat()} ~ {end.isoformat()}\n"
        f"- 周内优化轮次：{round_count}\n"
        f"- 周内新增证据总数：{total_new_evidence}\n"
        f"- 周内最高评分：{round(best_score, 4)}\n"
        f"- 引用日报数：{len(daily_used)}\n"
    )

    out_file = root / "paper_state" / "review" / "weekly" / f"{week_tag}.md"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    if out_file.exists() and not overwrite:
        raise ValueError("目标周报已存在，若需覆盖请传 overwrite=true")
    out_file.write_text(md, encoding="utf-8")

    payload = {
        "week_tag": week_tag,
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "path": str(out_file),
        "round_count": round_count,
        "new_evidence_total": total_new_evidence,
        "best_score": round(best_score, 4),
        "daily_used": daily_used,
    }
    state_path = None
    if write_state:
        state_path = _update_review_state(root, "weekly", payload)

    return {
        "ok": True,
        "week_tag": week_tag,
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "path": str(out_file),
        "round_count": round_count,
        "new_evidence_total": total_new_evidence,
        "best_score": round(best_score, 4),
        "daily_used": daily_used,
        "state_path": state_path,
    }

