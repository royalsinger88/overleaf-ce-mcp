"""论文工作流一键编排。"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .optimization_loop import run_optimization_loop
from .review import generate_daily_review, generate_weekly_summary


def _parse_day(raw: Optional[str]) -> _dt.date:
    if raw is None or not str(raw).strip():
        return _dt.date.today()
    try:
        return _dt.date.fromisoformat(str(raw).strip())
    except Exception as exc:
        raise ValueError("day 格式错误，应为 YYYY-MM-DD") from exc


def _weekly_switch(mode: str, day: _dt.date) -> bool:
    m = str(mode or "auto").strip().lower()
    if m not in ("auto", "always", "never"):
        raise ValueError("weekly_mode 仅支持 auto/always/never")
    if m == "always":
        return True
    if m == "never":
        return False
    return day.weekday() == 4  # 周五


def _write_cycle_summary(project_root: Path, payload: Dict[str, Any]) -> Dict[str, str]:
    out_dir = project_root / "paper_state" / "outputs" / "paper_cycle"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"cycle_{ts}.json"
    md_path = out_dir / f"cycle_{ts}.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines: List[str] = [
        "# Paper Cycle Summary",
        "",
        f"- 执行时间（UTC）：{payload.get('executed_at')}",
        f"- 目标日期：{payload.get('day')}",
        f"- weekly_mode：{payload.get('weekly_mode')}",
        f"- 已执行步骤：{', '.join(payload.get('executed_steps') or []) or '[无]'}",
        "",
        "## 结果摘要",
        f"- 优化循环：{'ok' if payload.get('loop') else 'skipped'}",
        f"- 每日复盘：{'ok' if payload.get('daily_review') else 'skipped'}",
        f"- 每周总结：{'ok' if payload.get('weekly_summary') else 'skipped'}",
    ]
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"summary_json": str(json_path), "summary_markdown": str(md_path)}


def run_paper_cycle(
    project_dir: str,
    day: Optional[str] = None,
    weekly_mode: str = "auto",
    run_loop: bool = True,
    run_daily: bool = True,
    overwrite_reviews: bool = True,
    write_state: bool = True,
    loop_config_path: Optional[str] = None,
    topic: Optional[str] = None,
    known_data: Optional[str] = None,
    writing_direction: Optional[str] = None,
    baseline_models: Optional[List[str]] = None,
    improvement_modules: Optional[List[str]] = None,
    target_journal: Optional[str] = None,
    constraints: Optional[str] = None,
    query: Optional[str] = None,
    source: Optional[str] = None,
    max_rounds: Optional[int] = None,
    min_score_improvement: Optional[float] = None,
    patience: Optional[int] = None,
    target_score: Optional[float] = None,
    max_results_per_source: Optional[int] = None,
    max_items_for_note: Optional[int] = None,
    num_prompts: Optional[int] = None,
    timeout: Optional[int] = None,
    s2_api_key: Optional[str] = None,
    enable_journal_recommendation: Optional[bool] = None,
    target_preference: Optional[str] = None,
    max_candidates: Optional[int] = None,
    append_claim_evidence: Optional[bool] = None,
    loop_write_daily_review: bool = False,
) -> Dict[str, Any]:
    root = Path(project_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("project_dir 不是有效目录: %s" % str(root))

    target_day = _parse_day(day)
    weekly_enabled = _weekly_switch(weekly_mode, target_day)
    executed_steps: List[str] = []

    loop_result: Optional[Dict[str, Any]] = None
    if run_loop:
        loop_result = run_optimization_loop(
            project_dir=str(root),
            loop_config_path=loop_config_path,
            topic=topic,
            known_data=known_data,
            writing_direction=writing_direction,
            baseline_models=baseline_models,
            improvement_modules=improvement_modules,
            target_journal=target_journal,
            constraints=constraints,
            query=query,
            source=source,
            max_rounds=max_rounds,
            min_score_improvement=min_score_improvement,
            patience=patience,
            target_score=target_score,
            max_results_per_source=max_results_per_source,
            max_items_for_note=max_items_for_note,
            num_prompts=num_prompts,
            timeout=timeout,
            s2_api_key=s2_api_key,
            enable_journal_recommendation=enable_journal_recommendation,
            target_preference=target_preference,
            max_candidates=max_candidates,
            write_daily_review=loop_write_daily_review,
            append_claim_evidence=append_claim_evidence,
        )
        executed_steps.append("optimization_loop")

    daily_result: Optional[Dict[str, Any]] = None
    if run_daily:
        daily_result = generate_daily_review(
            project_dir=str(root),
            day=target_day.isoformat(),
            overwrite=overwrite_reviews,
            write_state=write_state,
        )
        executed_steps.append("daily_review")

    weekly_result: Optional[Dict[str, Any]] = None
    if weekly_enabled:
        weekly_result = generate_weekly_summary(
            project_dir=str(root),
            anchor_day=target_day.isoformat(),
            overwrite=overwrite_reviews,
            write_state=write_state,
        )
        executed_steps.append("weekly_summary")

    payload: Dict[str, Any] = {
        "ok": True,
        "project_dir": str(root),
        "executed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "day": target_day.isoformat(),
        "weekly_mode": str(weekly_mode or "auto").strip().lower(),
        "weekly_enabled": weekly_enabled,
        "executed_steps": executed_steps,
        "loop": loop_result,
        "daily_review": daily_result,
        "weekly_summary": weekly_result,
    }
    payload["paths"] = _write_cycle_summary(root, payload)
    return payload

