"""论文写作优化循环编排。"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .deep_research import generate_deep_research_prompt_set, synthesize_paper_strategy
from .scholar import build_related_work_pack, recommend_target_journals


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: List[str] = []
        for x in value:
            s = str(x).strip()
            if s:
                out.append(s)
        return out
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    s = str(value).strip()
    return [s] if s else []


def _parse_scalar(value: str) -> Any:
    s = value.strip()
    if not s:
        return ""
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    low = s.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "none", "~"):
        return None
    if re.fullmatch(r"-?\d+", s):
        try:
            return int(s)
        except Exception:
            return s
    if re.fullmatch(r"-?\d+\.\d+", s):
        try:
            return float(s)
        except Exception:
            return s
    return s


def _load_simple_yaml(path: Path) -> Dict[str, Any]:
    """解析扁平 YAML（key: value）。

    该解析器仅用于 loop.yaml 的轻量配置场景，不支持复杂嵌套结构。
    """
    out: Dict[str, Any] = {}
    if not path.exists() or not path.is_file():
        raise ValueError("loop_config_path 不存在: %s" % str(path))

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        k = key.strip()
        if not k:
            continue
        out[k] = _parse_scalar(value)
    return out


def _read_if_file(project_dir: Path, value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (project_dir / raw).resolve()
    if p.exists() and p.is_file():
        return p.read_text(encoding="utf-8")
    return raw


def _read_project_title(project_dir: Path) -> Optional[str]:
    p = project_dir / "paper_state" / "inputs" / "project.yaml"
    if not p.exists() or not p.is_file():
        return None
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("title:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return None


def _paper_identity(paper: Dict[str, Any]) -> str:
    doi = str(paper.get("doi") or "").strip().lower()
    if doi:
        return "doi:" + doi
    aid = str(paper.get("arxiv_id") or "").strip().lower()
    if aid:
        return "arxiv:" + aid
    url = str(paper.get("url") or paper.get("pdf_url") or "").strip().lower()
    if url:
        return "url:" + url
    title = str(paper.get("title") or "").strip().lower()
    if title:
        return "title:" + title
    return ""


def _paper_source(paper: Dict[str, Any]) -> Tuple[str, str, str]:
    doi = str(paper.get("doi") or "").strip()
    if doi:
        return "doi", doi, "medium"
    aid = str(paper.get("arxiv_id") or "").strip()
    if aid:
        return "arxiv", aid, "medium"
    url = str(paper.get("url") or paper.get("pdf_url") or "").strip()
    if url:
        return "url", url, "low"
    title = str(paper.get("title") or "").strip()
    return "title", title, "low"


def _compose_round_markdown(round_data: Dict[str, Any]) -> str:
    idx = round_data["round_index"]
    titles = round_data.get("title_candidates") or []
    top_titles = "\n".join([f"- {x}" for x in titles[:5]]) if titles else "- [无]"
    return (
        f"# Optimization Round {idx}\n\n"
        f"- 阶段: `{round_data['stage']}`\n"
        f"- 评分: `{round_data['score']}`\n"
        f"- 较上轮提升: `{round_data['improvement']}`\n"
        f"- 新证据数: `{round_data['new_evidence_count']}`\n"
        f"- 文献候选数: `{round_data['paper_count']}`\n"
        f"- 可核验比例: `{round_data['verifiable_ratio']}`\n"
        f"- 提示词组数: `{round_data['prompt_count']}`\n\n"
        "## 标题候选（Top）\n"
        f"{top_titles}\n\n"
        "## 建议下一步\n"
        + "\n".join([f"- {x}" for x in round_data.get("next_actions", [])[:5]])
        + "\n"
    )


def _append_daily_review(review_path: Path, lines: List[str]) -> None:
    review_path.parent.mkdir(parents=True, exist_ok=True)
    block = "\n".join(lines).rstrip() + "\n"
    if review_path.exists():
        old = review_path.read_text(encoding="utf-8")
        if old and not old.endswith("\n"):
            old += "\n"
        review_path.write_text(old + "\n" + block, encoding="utf-8")
    else:
        review_path.write_text(block, encoding="utf-8")


def run_optimization_loop(
    project_dir: str,
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
    write_daily_review: Optional[bool] = None,
    append_claim_evidence: Optional[bool] = None,
) -> Dict[str, Any]:
    root = Path(project_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("project_dir 不是有效目录: %s" % str(root))

    config: Dict[str, Any] = {}
    cfg_path: Optional[Path] = None
    if loop_config_path:
        cfg_path = Path(loop_config_path).expanduser()
        if not cfg_path.is_absolute():
            cfg_path = (root / cfg_path).resolve()
        config = _load_simple_yaml(cfg_path)
    else:
        default_cfg = root / "paper_state" / "inputs" / "loop.yaml"
        if default_cfg.exists() and default_cfg.is_file():
            cfg_path = default_cfg
            config = _load_simple_yaml(default_cfg)

    def _get(name: str, current: Any) -> Any:
        if current is not None:
            return current
        return config.get(name)

    topic_v = _get("topic", topic)
    if topic_v is None or not str(topic_v).strip():
        topic_v = _read_project_title(root)
    if not topic_v or not str(topic_v).strip():
        raise ValueError("topic 不能为空（可在参数中提供，或在 paper_state/inputs/project.yaml 中配置 title）")
    topic_s = str(topic_v).strip()

    known_data_raw = _get("known_data", known_data)
    known_data_file = config.get("known_data_file") if known_data is None else None
    known_data_s = _read_if_file(root, str(known_data_file) if known_data_file else None) or _read_if_file(root, known_data_raw)
    if not known_data_s:
        brief = root / "paper_state" / "inputs" / "writing_brief.md"
        if brief.exists():
            known_data_s = brief.read_text(encoding="utf-8")
    if not known_data_s:
        raise ValueError("known_data 不能为空（可传 known_data 或 known_data_file）")

    writing_raw = _get("writing_direction", writing_direction)
    writing_file = config.get("writing_direction_file") if writing_direction is None else None
    writing_s = _read_if_file(root, str(writing_file) if writing_file else None) or _read_if_file(root, writing_raw)
    if not writing_s:
        writing_s = known_data_s
    if not writing_s:
        raise ValueError("writing_direction 不能为空")

    baselines = _to_list(_get("baseline_models", baseline_models))
    improves = _to_list(_get("improvement_modules", improvement_modules))

    target_journal_s = str(_get("target_journal", target_journal) or "").strip() or None
    constraints_s = str(_get("constraints", constraints) or "").strip() or None
    query_s = str(_get("query", query) or "").strip() or topic_s

    source_raw = source if source is not None else config.get("source", "all")
    source_s = str(source_raw or "all").strip() or "all"

    max_rounds_raw = max_rounds if max_rounds is not None else config.get("max_rounds", 4)
    max_rounds_i = max(1, min(_as_int(max_rounds_raw, 4), 12))

    min_score_raw = min_score_improvement if min_score_improvement is not None else config.get("min_score_improvement", 0.03)
    min_score_impr_f = max(0.0, min(_as_float(min_score_raw, 0.03), 1.0))

    patience_raw = patience if patience is not None else config.get("patience", 2)
    patience_i = max(1, min(_as_int(patience_raw, 2), 6))

    target_score_raw = target_score if target_score is not None else config.get("target_score", 0.85)
    target_score_f: Optional[float] = None
    if target_score_raw is not None:
        target_score_f = max(0.0, min(_as_float(target_score_raw, 0.85), 1.0))

    max_results_raw = (
        max_results_per_source if max_results_per_source is not None else config.get("max_results_per_source", 10)
    )
    max_results_i = max(3, min(_as_int(max_results_raw, 10), 50))

    max_items_raw = max_items_for_note if max_items_for_note is not None else config.get("max_items_for_note", 8)
    max_items_i = max(3, min(_as_int(max_items_raw, 8), 20))

    num_prompts_raw = num_prompts if num_prompts is not None else config.get("num_prompts", 6)
    num_prompts_i = max(2, min(_as_int(num_prompts_raw, 6), 6))

    timeout_raw = timeout if timeout is not None else config.get("timeout", 30)
    timeout_i = max(5, min(_as_int(timeout_raw, 30), 120))

    enable_journal_raw = (
        enable_journal_recommendation
        if enable_journal_recommendation is not None
        else config.get("enable_journal_recommendation", True)
    )
    enable_journal = _as_bool(enable_journal_raw, True)

    target_pref_raw = target_preference if target_preference is not None else config.get("target_preference", "any")
    target_pref_s = str(target_pref_raw or "any").strip()

    max_candidates_raw = max_candidates if max_candidates is not None else config.get("max_candidates", 5)
    max_candidates_i = max(3, min(_as_int(max_candidates_raw, 5), 10))

    write_daily_raw = write_daily_review if write_daily_review is not None else config.get("write_daily_review", True)
    write_daily = _as_bool(write_daily_raw, True)

    append_claim_raw = (
        append_claim_evidence if append_claim_evidence is not None else config.get("append_claim_evidence", True)
    )
    append_claim = _as_bool(append_claim_raw, True)

    outputs_root = root / "paper_state" / "outputs" / "optimization_loop"
    outputs_root.mkdir(parents=True, exist_ok=True)
    review_daily_path = root / "paper_state" / "review" / "daily" / f"{_dt.date.today().isoformat()}.md"
    claim_file = root / "paper_state" / "memory" / "claim_evidence.jsonl"
    claim_file.parent.mkdir(parents=True, exist_ok=True)
    if not claim_file.exists():
        claim_file.write_text("", encoding="utf-8")

    rounds: List[Dict[str, Any]] = []
    seen_evidence: Set[str] = set()
    report_summaries: List[str] = []
    prev_score = 0.0
    no_gain_rounds = 0
    no_new_evidence_rounds = 0
    stop_reason = "max_rounds_reached"

    for idx in range(1, max_rounds_i + 1):
        stage = "r1" if idx == 1 else "r2"
        prior = "\n".join(report_summaries[-3:]) if report_summaries else None

        prompt_set = generate_deep_research_prompt_set(
            topic=topic_s,
            known_data=known_data_s,
            writing_direction=writing_s,
            baseline_models=baselines,
            improvement_modules=improves,
            target_journal=target_journal_s,
            constraints=constraints_s,
            round_stage=stage,
            prior_findings=prior,
            max_references=30,
            num_prompts=num_prompts_i,
        )

        related = build_related_work_pack(
            query=query_s,
            source=source_s,
            max_results_per_source=max_results_i,
            max_items_for_note=max_items_i,
            timeout=timeout_i,
            s2_api_key=s2_api_key,
        )

        strategy = synthesize_paper_strategy(
            topic=topic_s,
            target_journal=target_journal_s,
            baseline_models=baselines,
            improvement_modules=improves,
            key_results=known_data_s[:1200],
            report_summaries=report_summaries[-5:],
            constraints=constraints_s,
            candidate_title_count=6,
        )

        journal_rec: Optional[Dict[str, Any]] = None
        if enable_journal:
            journal_rec = recommend_target_journals(
                topic=topic_s,
                target_preference=target_pref_s,
                max_candidates=max_candidates_i,
                max_results_per_source=max_results_i,
                timeout=timeout_i,
                s2_api_key=s2_api_key,
            )

        papers = related.get("papers") if isinstance(related.get("papers"), list) else []
        paper_count = len(papers)
        verifiable_count = 0
        new_ids: List[str] = []
        for p in papers:
            if not isinstance(p, dict):
                continue
            pid = _paper_identity(p)
            if pid:
                if pid not in seen_evidence:
                    new_ids.append(pid)
                    seen_evidence.add(pid)
            if p.get("doi") or p.get("arxiv_id") or p.get("url") or p.get("pdf_url"):
                verifiable_count += 1

        verifiable_ratio = round((verifiable_count / paper_count), 4) if paper_count > 0 else 0.0
        new_evidence_count = len(new_ids)

        titles = strategy.get("recommended_titles") if isinstance(strategy.get("recommended_titles"), list) else []
        innovation_points = strategy.get("innovation_points") if isinstance(strategy.get("innovation_points"), list) else []
        journal_fit = 0.0
        if journal_rec and isinstance(journal_rec.get("recommendations"), list) and journal_rec.get("recommendations"):
            top_score_raw = journal_rec["recommendations"][0].get("score", 0)
            top_score = _as_float(top_score_raw, 0.0)
            journal_fit = max(0.0, min(top_score / 5.0, 1.0))

        coverage = max(0.0, min((paper_count / float(max_items_i)), 1.0))
        innovation_strength = max(0.0, min((len(innovation_points) / 4.0), 1.0))
        score = round(0.35 * coverage + 0.35 * verifiable_ratio + 0.20 * innovation_strength + 0.10 * journal_fit, 4)
        improvement = round(score - prev_score, 4)

        if improvement < min_score_impr_f:
            no_gain_rounds += 1
        else:
            no_gain_rounds = 0

        if new_evidence_count <= 0:
            no_new_evidence_rounds += 1
        else:
            no_new_evidence_rounds = 0

        next_actions = strategy.get("next_actions") if isinstance(strategy.get("next_actions"), list) else []
        round_data: Dict[str, Any] = {
            "round_index": idx,
            "stage": stage,
            "score": score,
            "improvement": improvement,
            "paper_count": paper_count,
            "verifiable_count": verifiable_count,
            "verifiable_ratio": verifiable_ratio,
            "new_evidence_count": new_evidence_count,
            "prompt_count": prompt_set.get("count", 0),
            "title_candidates": titles,
            "innovation_points": innovation_points,
            "next_actions": next_actions,
            "journal_recommendation_top": (
                (journal_rec.get("recommendations") or [None])[0] if journal_rec else None
            ),
            "paths": {},
        }

        round_dir = outputs_root / f"round_{idx:02d}"
        round_dir.mkdir(parents=True, exist_ok=True)
        round_json_path = round_dir / "round_result.json"
        round_md_path = round_dir / "round_summary.md"
        round_json_path.write_text(json.dumps(round_data, ensure_ascii=False, indent=2), encoding="utf-8")
        round_md_path.write_text(_compose_round_markdown(round_data), encoding="utf-8")
        round_data["paths"] = {
            "round_dir": str(round_dir),
            "round_json": str(round_json_path),
            "round_markdown": str(round_md_path),
        }

        # 记录“可追溯证据候选”，用于下一轮写作核验。
        if append_claim and papers:
            with claim_file.open("a", encoding="utf-8") as fw:
                keep = 0
                for p in papers:
                    if not isinstance(p, dict):
                        continue
                    source_type, source_value, confidence = _paper_source(p)
                    if not source_value:
                        continue
                    keep += 1
                    row = {
                        "claim_id": f"LOOP-R{idx:02d}-E{keep:02d}",
                        "claim": f"Round {idx} candidate evidence: {str(p.get('title') or '[untitled]')}",
                        "source_type": source_type,
                        "source": source_value,
                        "confidence": confidence,
                        "status": "candidate",
                        "note": "auto-appended by run_optimization_loop",
                    }
                    fw.write(json.dumps(row, ensure_ascii=False) + "\n")
                    if keep >= 3:
                        break

        report_summaries.append(
            f"Round {idx}: score={score}, new_evidence={new_evidence_count}, titles={len(titles)}"
        )
        rounds.append(round_data)

        if write_daily:
            _append_daily_review(
                review_daily_path,
                [
                    f"## Optimization Loop - Round {idx}",
                    f"- 评分：{score}（提升 {improvement}）",
                    f"- 新证据：{new_evidence_count}，候选文献：{paper_count}，可核验比例：{verifiable_ratio}",
                    f"- 停止计数：no_gain={no_gain_rounds}/{patience_i}, no_new_evidence={no_new_evidence_rounds}/{patience_i}",
                    "- 下一步：" + (next_actions[0] if next_actions else "[待补充]"),
                ],
            )

        prev_score = score

        if target_score_f is not None and score >= target_score_f:
            stop_reason = "target_score_reached"
            break
        if no_gain_rounds >= patience_i:
            stop_reason = "stagnation_no_gain"
            break
        if no_new_evidence_rounds >= patience_i:
            stop_reason = "stagnation_no_new_evidence"
            break

    summary = {
        "ok": True,
        "project_dir": str(root),
        "loop_config_path": str(cfg_path) if cfg_path else None,
        "stop_reason": stop_reason,
        "round_count": len(rounds),
        "params": {
            "topic": topic_s,
            "query": query_s,
            "source": source_s,
            "max_rounds": max_rounds_i,
            "min_score_improvement": min_score_impr_f,
            "patience": patience_i,
            "target_score": target_score_f,
            "max_results_per_source": max_results_i,
            "max_items_for_note": max_items_i,
            "num_prompts": num_prompts_i,
            "enable_journal_recommendation": enable_journal,
            "target_preference": target_pref_s,
            "max_candidates": max_candidates_i,
        },
        "rounds": rounds,
        "paths": {
            "outputs_root": str(outputs_root),
            "summary_json": str(outputs_root / "loop_summary.json"),
            "summary_markdown": str(outputs_root / "loop_summary.md"),
            "daily_review": str(review_daily_path) if write_daily else None,
            "claim_evidence": str(claim_file) if append_claim else None,
        },
    }

    summary_md = [
        "# Optimization Loop Summary",
        "",
        f"- 停止原因: `{stop_reason}`",
        f"- 轮数: `{len(rounds)}`",
        f"- 主题: `{topic_s}`",
        f"- 查询: `{query_s}`",
        "",
        "## 每轮摘要",
    ]
    for r in rounds:
        summary_md.append(
            f"- Round {r['round_index']}: score={r['score']}, improvement={r['improvement']}, "
            f"new_evidence={r['new_evidence_count']}, paper_count={r['paper_count']}"
        )

    summary_json_path = outputs_root / "loop_summary.json"
    summary_md_path = outputs_root / "loop_summary.md"
    summary_json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_md_path.write_text("\n".join(summary_md).rstrip() + "\n", encoding="utf-8")

    return summary
