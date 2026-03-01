"""论文工作流一键编排。"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
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


def _read_text(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _strip_quotes(text: str) -> str:
    s = text.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1].strip()
    return s


def _read_yaml_scalar(path: Path, key: str) -> Optional[str]:
    text = _read_text(path)
    if not text:
        return None
    pat = re.compile(rf"^\s*{re.escape(key)}\s*:\s*(.*?)\s*$", re.MULTILINE)
    m = pat.search(text)
    if not m:
        return None
    raw = m.group(1).split("#", 1)[0].strip()
    if not raw:
        return None
    val = _strip_quotes(raw)
    if val in ("null", "None", "none", "[]", "{}"):
        return None
    return val


def _split_csv_like(raw: Optional[str]) -> List[str]:
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    return [x.strip() for x in text.split(",") if x.strip()]


def _clean_placeholder_lines(text: str) -> str:
    out: List[str] = []
    for ln in text.splitlines():
        s = ln.strip()
        low = s.lower()
        if not s:
            continue
        if s.startswith("#"):
            continue
        if s in ("[补充]", "- [补充]", "TODO", "- TODO", "- [todo]"):
            continue
        if low in ("[todo]", "tbd"):
            continue
        out.append(ln)
    return "\n".join(out).strip()


def _extract_md_section(text: str, headings: List[str]) -> Optional[str]:
    if not text.strip():
        return None
    wanted = {h.strip().lower().replace(" ", "") for h in headings if h.strip()}
    lines = text.splitlines()
    start = -1
    for i, raw in enumerate(lines):
        ln = raw.strip()
        if not ln.startswith("#"):
            continue
        title = ln.lstrip("#").strip().lower().replace(" ", "")
        if title in wanted:
            start = i + 1
            break
    if start < 0:
        return None
    buf: List[str] = []
    for j in range(start, len(lines)):
        cur = lines[j].strip()
        if cur.startswith("#"):
            break
        buf.append(lines[j])
    cleaned = _clean_placeholder_lines("\n".join(buf))
    return cleaned if cleaned else None


def _extract_seed_query(path: Path) -> Dict[str, Optional[str]]:
    text = _read_text(path) or ""
    q = None
    src = None
    for raw in text.splitlines():
        ln = raw.strip()
        if q is None:
            m = re.match(r'^text\s*:\s*["\']?(.*?)["\']?$', ln)
            if m:
                v = _strip_quotes(m.group(1))
                if v:
                    q = v
                    continue
        if src is None:
            m2 = re.match(r'^source\s*:\s*["\']?(.*?)["\']?$', ln)
            if m2:
                v2 = _strip_quotes(m2.group(1))
                if v2:
                    src = v2
                    continue
        if q and src:
            break
    return {"query": q, "source": src}


def _extract_constraints(path: Path) -> Optional[str]:
    text = _read_text(path) or ""
    if not text.strip():
        return None
    kept: List[str] = []
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln or ln.startswith("#") or ":" not in ln:
            continue
        key, value = ln.split(":", 1)
        k = key.strip()
        v = _strip_quotes(value.strip())
        if not v or v in ("null", "None", "none", "[]", "{}", '""'):
            continue
        kept.append(f"{k}={v}")
    return "; ".join(kept) if kept else None


def _count_csv_rows(path: Path) -> int:
    text = _read_text(path) or ""
    if not text.strip():
        return 0
    lines = [x for x in text.splitlines() if x.strip()]
    if len(lines) <= 1:
        return 0
    return len(lines) - 1


def _write_missing_checklist(
    project_root: Path,
    target_day: _dt.date,
    missing_items: List[str],
    profile: Dict[str, Any],
    overwrite: bool = True,
) -> Optional[str]:
    if not missing_items:
        return None
    fp = project_root / "paper_state" / "inputs" / "INPUT_MISSING.md"
    if fp.exists() and not overwrite:
        return str(fp)
    lines = [
        f"# Inputs Missing Checklist - {target_day.isoformat()}",
        "",
        "以下素材缺失或质量不足，建议补齐后再执行新一轮：",
    ]
    for x in missing_items:
        lines.append(f"- {x}")
    lines.extend(
        [
            "",
            "## 自动扫描概况",
            f"- writing_brief_exists: {profile.get('writing_brief_exists')}",
            f"- submission_target_exists: {profile.get('submission_target_exists')}",
            f"- constraints_exists: {profile.get('constraints_exists')}",
            f"- seed_queries_exists: {profile.get('seed_queries_exists')}",
            f"- experiment_registry_rows: {profile.get('experiment_registry_rows')}",
        ]
    )
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return str(fp)


def _collect_auto_materials(project_root: Path) -> Dict[str, Any]:
    inputs = project_root / "paper_state" / "inputs"
    profile: Dict[str, Any] = {}

    project_yaml = inputs / "project.yaml"
    writing_brief = inputs / "writing_brief.md"
    submission_target = inputs / "submission_target.yaml"
    constraints_yaml = inputs / "constraints.yaml"
    loop_yaml = inputs / "loop.yaml"
    seed_queries = inputs / "literature" / "seed_queries.yaml"
    exp_registry = inputs / "experiments" / "registry.csv"

    profile["project_yaml_exists"] = project_yaml.exists()
    profile["writing_brief_exists"] = writing_brief.exists()
    profile["submission_target_exists"] = submission_target.exists()
    profile["constraints_exists"] = constraints_yaml.exists()
    profile["loop_yaml_exists"] = loop_yaml.exists()
    profile["seed_queries_exists"] = seed_queries.exists()
    profile["experiment_registry_rows"] = _count_csv_rows(exp_registry)

    topic = _read_yaml_scalar(project_yaml, "title")

    wb_text = _read_text(writing_brief) or ""
    known_data = _extract_md_section(wb_text, ["当前证据", "关键实验数据", "实验结果", "currentevidence", "keyresults"])
    if not known_data:
        cleaned = _clean_placeholder_lines(wb_text)
        known_data = cleaned if cleaned else None

    rq = _extract_md_section(wb_text, ["研究问题", "researchquestion"])
    ip = _extract_md_section(wb_text, ["预期创新点", "创新点", "contribution"])
    rk = _extract_md_section(wb_text, ["当前风险", "风险", "risk"])
    writing_parts = [x for x in (rq, ip, rk) if x]
    writing_direction = "\n\n".join(writing_parts).strip() if writing_parts else None
    if not writing_direction:
        writing_direction = known_data

    target_journal = _read_yaml_scalar(submission_target, "primary_target_journal")
    if not target_journal:
        target_journal = _read_yaml_scalar(loop_yaml, "target_journal")

    constraints = _extract_constraints(constraints_yaml)
    if not constraints:
        constraints = _read_yaml_scalar(loop_yaml, "constraints")

    query = _read_yaml_scalar(loop_yaml, "query")
    source = _read_yaml_scalar(loop_yaml, "source")
    if not query or not source:
        sq = _extract_seed_query(seed_queries)
        if not query:
            query = sq.get("query")
        if not source:
            source = sq.get("source")

    baseline_models = _split_csv_like(_read_yaml_scalar(loop_yaml, "baseline_models"))
    improvement_modules = _split_csv_like(_read_yaml_scalar(loop_yaml, "improvement_modules"))

    missing_items: List[str] = []
    if not known_data:
        missing_items.append("known_data（当前证据/关键实验数据）")
    if not writing_direction:
        missing_items.append("writing_direction（研究问题/创新点/风险）")
    if not query:
        missing_items.append("query（seed_queries 或 loop.yaml）")
    if profile["experiment_registry_rows"] <= 0:
        missing_items.append("experiments/registry.csv（至少 1 条实验记录）")

    return {
        "topic": topic,
        "known_data": known_data,
        "writing_direction": writing_direction,
        "target_journal": target_journal,
        "constraints": constraints,
        "query": query,
        "source": source,
        "baseline_models": baseline_models,
        "improvement_modules": improvement_modules,
        "missing_items": missing_items,
        "profile": profile,
    }


def _write_material_scan(project_root: Path, target_day: _dt.date, payload: Dict[str, Any]) -> Dict[str, str]:
    out_dir = project_root / "paper_state" / "outputs" / "paper_cycle"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"material_scan_{ts}.json"
    md_path = out_dir / f"material_scan_{ts}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# Material Scan - {target_day.isoformat()}",
        "",
        "## 自动识别结果",
        f"- topic: {payload.get('topic') or '[缺失]'}",
        f"- target_journal: {payload.get('target_journal') or '[缺失]'}",
        f"- query: {payload.get('query') or '[缺失]'}",
        f"- source: {payload.get('source') or '[缺失]'}",
        f"- baseline_models: {len(payload.get('baseline_models') or [])}",
        f"- improvement_modules: {len(payload.get('improvement_modules') or [])}",
        "",
        "## 缺失项",
    ]
    miss = payload.get("missing_items") or []
    if miss:
        for x in miss:
            lines.append(f"- {x}")
    else:
        lines.append("- [无]")
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"scan_json": str(json_path), "scan_markdown": str(md_path)}


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


def _loop_cache_key(effective: Dict[str, Any]) -> str:
    raw = json.dumps(effective, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _loop_cache_path(project_root: Path, cache_key: str) -> Path:
    d = project_root / "paper_state" / "cache" / "paper_cycle"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{cache_key}.json"


def _load_loop_cache(path: Path, ttl_hours: int) -> Optional[Dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return None
    age_seconds = (_dt.datetime.now(_dt.timezone.utc).timestamp() - path.stat().st_mtime)
    if age_seconds > max(1, int(ttl_hours)) * 3600:
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    data = obj.get("loop_result")
    if not isinstance(data, dict):
        return None
    return {"loop_result": data, "cached_at": obj.get("cached_at"), "cache_key": obj.get("cache_key")}


def _save_loop_cache(path: Path, cache_key: str, loop_result: Dict[str, Any]) -> None:
    payload = {
        "cache_key": cache_key,
        "cached_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "loop_result": loop_result,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_paper_cycle(
    project_dir: str,
    day: Optional[str] = None,
    weekly_mode: str = "auto",
    run_loop: bool = True,
    run_daily: bool = True,
    overwrite_reviews: bool = True,
    write_state: bool = True,
    auto_scan_inputs: bool = True,
    write_missing_checklist: bool = True,
    strict_missing: bool = False,
    use_cache: bool = True,
    cache_ttl_hours: int = 24,
    force_refresh: bool = False,
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
    auto_info: Dict[str, Any] = {"enabled": auto_scan_inputs}
    cache_info: Dict[str, Any] = {"enabled": bool(use_cache), "hit": False}

    eff_topic = topic
    eff_known_data = known_data
    eff_writing_direction = writing_direction
    eff_baseline_models = baseline_models
    eff_improvement_modules = improvement_modules
    eff_target_journal = target_journal
    eff_constraints = constraints
    eff_query = query
    eff_source = source

    if auto_scan_inputs:
        auto_raw = _collect_auto_materials(root)
        if eff_topic is None:
            eff_topic = auto_raw.get("topic")
        if eff_known_data is None:
            eff_known_data = auto_raw.get("known_data")
        if eff_writing_direction is None:
            eff_writing_direction = auto_raw.get("writing_direction")
        if eff_target_journal is None:
            eff_target_journal = auto_raw.get("target_journal")
        if eff_constraints is None:
            eff_constraints = auto_raw.get("constraints")
        if eff_query is None:
            eff_query = auto_raw.get("query")
        if eff_source is None:
            eff_source = auto_raw.get("source")
        if eff_baseline_models is None:
            eff_baseline_models = auto_raw.get("baseline_models")
        if eff_improvement_modules is None:
            eff_improvement_modules = auto_raw.get("improvement_modules")

        missing_items = auto_raw.get("missing_items") or []
        scan_paths = _write_material_scan(root, target_day, auto_raw)
        checklist_path = None
        if write_missing_checklist:
            checklist_path = _write_missing_checklist(
                project_root=root,
                target_day=target_day,
                missing_items=missing_items,
                profile=auto_raw.get("profile") or {},
            )
        auto_info = {
            "enabled": True,
            "resolved": {
                "topic": bool(eff_topic),
                "known_data": bool(eff_known_data),
                "writing_direction": bool(eff_writing_direction),
                "target_journal": bool(eff_target_journal),
                "constraints": bool(eff_constraints),
                "query": bool(eff_query),
                "source": bool(eff_source),
            },
            "missing_items": missing_items,
            "profile": auto_raw.get("profile") or {},
            "paths": {
                **scan_paths,
                "missing_checklist": checklist_path,
            },
        }
        if strict_missing and missing_items:
            raise ValueError("inputs 素材缺失，请先补齐 INPUT_MISSING.md 后重试")

    loop_result: Optional[Dict[str, Any]] = None
    if run_loop:
        effective_for_cache = {
            "topic": eff_topic,
            "known_data": eff_known_data,
            "writing_direction": eff_writing_direction,
            "baseline_models": eff_baseline_models,
            "improvement_modules": eff_improvement_modules,
            "target_journal": eff_target_journal,
            "constraints": eff_constraints,
            "query": eff_query,
            "source": eff_source,
            "max_rounds": max_rounds,
            "min_score_improvement": min_score_improvement,
            "patience": patience,
            "target_score": target_score,
            "max_results_per_source": max_results_per_source,
            "max_items_for_note": max_items_for_note,
            "num_prompts": num_prompts,
            "timeout": timeout,
            "enable_journal_recommendation": enable_journal_recommendation,
            "target_preference": target_preference,
            "max_candidates": max_candidates,
            "append_claim_evidence": append_claim_evidence,
            "loop_write_daily_review": loop_write_daily_review,
        }
        cache_key = _loop_cache_key(effective_for_cache)
        cache_path = _loop_cache_path(root, cache_key)
        cache_info["cache_key"] = cache_key
        cache_info["cache_path"] = str(cache_path)

        cached = None
        if use_cache and not force_refresh:
            cached = _load_loop_cache(cache_path, ttl_hours=max(1, int(cache_ttl_hours)))
        if cached:
            loop_result = cached["loop_result"]
            cache_info["hit"] = True
            cache_info["cached_at"] = cached.get("cached_at")
            executed_steps.append("optimization_loop(cache)")
        else:
            cache_info["hit"] = False
            loop_result = run_optimization_loop(
                project_dir=str(root),
                loop_config_path=loop_config_path,
                topic=eff_topic,
                known_data=eff_known_data,
                writing_direction=eff_writing_direction,
                baseline_models=eff_baseline_models,
                improvement_modules=eff_improvement_modules,
                target_journal=eff_target_journal,
                constraints=eff_constraints,
                query=eff_query,
                source=eff_source,
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
            if use_cache and isinstance(loop_result, dict):
                _save_loop_cache(cache_path, cache_key, loop_result)

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
        "auto_inputs": auto_info,
        "cache": cache_info,
        "loop": loop_result,
        "daily_review": daily_result,
        "weekly_summary": weekly_result,
    }
    payload["paths"] = _write_cycle_summary(root, payload)
    return payload
