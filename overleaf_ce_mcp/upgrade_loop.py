"""按优先级循环执行工程改造任务（upgrade loop）。"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .evidence_binding import run_manuscript_evidence_binding
from .paper_doctor import run_paper_doctor
from .scheduler import generate_scheduler_templates
from .workflow import run_paper_cycle


def _task_catalog() -> List[Dict[str, Any]]:
    return [
        {
            "id": "paper_doctor",
            "title": "paper_state 输入规范校验器（paper_doctor）",
            "impact": 10,
            "effort": 2,
            "dependencies": [],
        },
        {
            "id": "run_and_sync_overleaf",
            "title": "一键执行并同步到 Overleaf",
            "impact": 9,
            "effort": 4,
            "dependencies": ["paper_doctor"],
        },
        {
            "id": "manuscript_evidence_binding",
            "title": "手稿证据绑定（段落-证据覆盖率）",
            "impact": 8,
            "effort": 4,
            "dependencies": ["paper_doctor"],
        },
        {
            "id": "incremental_cache",
            "title": "增量执行与缓存",
            "impact": 8,
            "effort": 3,
            "dependencies": ["paper_doctor"],
        },
        {
            "id": "resume_checkpoint",
            "title": "失败恢复与断点续跑",
            "impact": 7,
            "effort": 3,
            "dependencies": ["incremental_cache"],
        },
        {
            "id": "scheduler_templates",
            "title": "可配置调度模板（cron/systemd）",
            "impact": 6,
            "effort": 2,
            "dependencies": ["run_and_sync_overleaf"],
        },
    ]


def _state_path(project_root: Path) -> Path:
    p = project_root / "paper_state" / "memory" / "upgrade_loop_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_state(project_root: Path) -> Dict[str, Any]:
    fp = _state_path(project_root)
    if not fp.exists():
        return {"completed": {}, "history": []}
    try:
        obj = json.loads(fp.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            return {
                "completed": obj.get("completed") if isinstance(obj.get("completed"), dict) else {},
                "history": obj.get("history") if isinstance(obj.get("history"), list) else [],
            }
    except Exception:
        pass
    return {"completed": {}, "history": []}


def _save_state(project_root: Path, state: Dict[str, Any]) -> str:
    fp = _state_path(project_root)
    state["updated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    fp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(fp)


def _rank_tasks(state: Dict[str, Any], task_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    done = state.get("completed") if isinstance(state.get("completed"), dict) else {}
    allowed = set(task_ids) if task_ids else None
    tasks = []
    for t in _task_catalog():
        tid = t["id"]
        if allowed is not None and tid not in allowed:
            continue
        completed = bool(done.get(tid, {}).get("ok"))
        dep_penalty = 0
        for dep in t.get("dependencies") or []:
            if not bool(done.get(dep, {}).get("ok")):
                dep_penalty += 2
        score = round((t["impact"] * 2.0) - (t["effort"] * 1.0) - dep_penalty, 2)
        row = dict(t)
        row["priority_score"] = score
        row["completed"] = completed
        tasks.append(row)
    tasks.sort(key=lambda x: (x["priority_score"], x["impact"]), reverse=True)
    return tasks


def _write_upgrade_reports(project_root: Path, payload: Dict[str, Any]) -> Dict[str, str]:
    out_dir = project_root / "paper_state" / "outputs" / "upgrade_loop"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    jp = out_dir / f"upgrade_{ts}.json"
    mp = out_dir / f"upgrade_{ts}.md"
    latest_json = out_dir / "latest.json"
    latest_md = out_dir / "latest.md"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    jp.write_text(text, encoding="utf-8")
    latest_json.write_text(text, encoding="utf-8")

    lines = [
        "# Upgrade Loop Summary",
        "",
        f"- 时间（UTC）：{payload.get('executed_at')}",
        f"- dry_run：{payload.get('dry_run')}",
        f"- 执行任务数：{len(payload.get('executed') or [])}",
        "",
        "## 任务执行",
    ]
    for e in payload.get("executed") or []:
        lines.append(
            f"- {e.get('task_id')} | ok={e.get('ok')} | status={e.get('status')} | "
            f"priority={e.get('priority_score')}"
        )
    if not (payload.get("executed") or []):
        lines.append("- [无]")
    md_text = "\n".join(lines).rstrip() + "\n"
    mp.write_text(md_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    return {
        "summary_json": str(jp),
        "summary_markdown": str(mp),
        "latest_json": str(latest_json),
        "latest_markdown": str(latest_md),
    }


def _setup_incremental_cache(project_root: Path) -> Dict[str, Any]:
    cache_dir = project_root / "paper_state" / "cache" / "paper_cycle"
    opt_cache_dir = project_root / "paper_state" / "cache" / "optimization_loop"
    cache_dir.mkdir(parents=True, exist_ok=True)
    opt_cache_dir.mkdir(parents=True, exist_ok=True)
    policy = project_root / "paper_state" / "cache" / "policy.yaml"
    if not policy.exists():
        policy.write_text(
            "cache:\n"
            "  paper_cycle_enabled: true\n"
            "  optimization_loop_enabled: true\n"
            "  default_ttl_hours: 24\n"
            "  force_refresh: false\n",
            encoding="utf-8",
        )
    readme = project_root / "paper_state" / "cache" / "README.md"
    if not readme.exists():
        readme.write_text(
            "# 增量缓存\n\n"
            "- `paper_cycle` 缓存目录：`paper_state/cache/paper_cycle`\n"
            "- `optimization_loop` 缓存目录：`paper_state/cache/optimization_loop/*`\n"
            "- 可通过 `run_paper_cycle(use_cache=true|false, force_refresh=true|false)` 控制。\n"
            "- 也可在 `run_optimization_loop` 中单独设置 `use_cache/cache_ttl_hours/force_refresh`。\n",
            encoding="utf-8",
        )
    return {
        "ok": True,
        "cache_dirs": {"paper_cycle": str(cache_dir), "optimization_loop": str(opt_cache_dir)},
        "policy_file": str(policy),
        "readme": str(readme),
    }


def _run_cycle_and_sync(
    project_root: Path,
    day: Optional[str],
    weekly_mode: str,
    run_loop: bool,
    run_daily: bool,
    ce_url: Optional[str],
    store_path: Optional[str],
    project_name: Optional[str],
    sync_mode: str,
) -> Dict[str, Any]:
    cycle = run_paper_cycle(
        project_dir=str(project_root),
        day=day,
        weekly_mode=weekly_mode,
        run_loop=run_loop,
        run_daily=run_daily,
        auto_scan_inputs=True,
        write_missing_checklist=True,
        run_compile=True,
        sync_mode=sync_mode,
        ce_url=ce_url,
        store_path=store_path,
        project_name=project_name,
        compile_check=True,
    )
    delivery = cycle.get("delivery") if isinstance(cycle, dict) else {}
    if not isinstance(delivery, dict):
        delivery = {}
    return {
        "ok": bool(cycle.get("ok")),
        "cycle": cycle,
        "local_compile": delivery.get("local_compile"),
        "remote": delivery.get("remote"),
    }


def _touch_resume_checkpoint(project_root: Path) -> Dict[str, Any]:
    fp = project_root / "paper_state" / "memory" / "upgrade_checkpoint.md"
    fp.parent.mkdir(parents=True, exist_ok=True)
    if not fp.exists():
        fp.write_text(
            "# Upgrade Loop Checkpoint\n\n"
            "- 说明：upgrade_loop 的断点信息保存在 `upgrade_loop_state.json`。\n"
            "- 若任务中断，重新执行 `run_priority_upgrade_loop(resume=true)` 将自动从未完成任务继续。\n",
            encoding="utf-8",
        )
    return {"ok": True, "checkpoint_note": str(fp)}


def list_upgrade_tasks(project_dir: str, include_completed: bool = True) -> Dict[str, Any]:
    root = Path(project_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("project_dir 不是有效目录: %s" % str(root))
    state = _load_state(root)
    ranked = _rank_tasks(state)
    if not include_completed:
        ranked = [x for x in ranked if not x.get("completed")]
    return {"ok": True, "project_dir": str(root), "count": len(ranked), "tasks": ranked}


def run_priority_upgrade_loop(
    project_dir: str,
    task_ids: Optional[List[str]] = None,
    max_tasks: int = 6,
    dry_run: bool = False,
    continue_on_error: bool = True,
    resume: bool = True,
    day: Optional[str] = None,
    weekly_mode: str = "auto",
    run_loop: bool = True,
    run_daily: bool = True,
    ce_url: Optional[str] = None,
    store_path: Optional[str] = None,
    project_name: Optional[str] = None,
    sync_mode: str = "none",
) -> Dict[str, Any]:
    root = Path(project_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("project_dir 不是有效目录: %s" % str(root))

    state = _load_state(root) if resume else {"completed": {}, "history": []}
    ranked = _rank_tasks(state, task_ids=task_ids)
    todo = [x for x in ranked if not x.get("completed")]
    todo = todo[: max(1, int(max_tasks))]

    executed: List[Dict[str, Any]] = []
    completed = state.get("completed") if isinstance(state.get("completed"), dict) else {}
    history = state.get("history") if isinstance(state.get("history"), list) else []

    for task in todo:
        tid = task["id"]
        row: Dict[str, Any] = {
            "task_id": tid,
            "title": task["title"],
            "priority_score": task["priority_score"],
            "started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        try:
            if dry_run:
                row["ok"] = True
                row["status"] = "planned"
                row["result"] = {"dry_run": True}
            else:
                if tid == "paper_doctor":
                    result = run_paper_doctor(project_dir=str(root), write_report=True)
                elif tid == "manuscript_evidence_binding":
                    result = run_manuscript_evidence_binding(project_dir=str(root), include_sections=True, write_report=True)
                elif tid == "incremental_cache":
                    result = _setup_incremental_cache(root)
                elif tid == "run_and_sync_overleaf":
                    result = _run_cycle_and_sync(
                        project_root=root,
                        day=day,
                        weekly_mode=weekly_mode,
                        run_loop=run_loop,
                        run_daily=run_daily,
                        ce_url=ce_url,
                        store_path=store_path,
                        project_name=project_name,
                        sync_mode=sync_mode,
                    )
                elif tid == "scheduler_templates":
                    result = generate_scheduler_templates(
                        project_dir=str(root),
                        repo_dir=str(Path(__file__).resolve().parent.parent),
                        python_bin="/usr/bin/python3",
                        daily_time="23:10",
                    )
                elif tid == "resume_checkpoint":
                    result = _touch_resume_checkpoint(root)
                else:
                    raise ValueError(f"未知任务: {tid}")
                row["ok"] = bool(result.get("ok", True))
                row["status"] = "done" if row["ok"] else "failed"
                row["result"] = result
            row["finished_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
            if row.get("ok"):
                completed[tid] = {
                    "ok": True,
                    "finished_at": row["finished_at"],
                    "priority_score": row["priority_score"],
                }
        except Exception as exc:
            row["ok"] = False
            row["status"] = "error"
            row["error"] = str(exc)
            row["finished_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
            if not continue_on_error:
                executed.append(row)
                history.append(row)
                break

        executed.append(row)
        history.append(row)

    state["completed"] = completed
    state["history"] = history[-200:]
    state_path = _save_state(root, state)

    summary: Dict[str, Any] = {
        "ok": all(bool(x.get("ok")) for x in executed) if executed else True,
        "project_dir": str(root),
        "executed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "dry_run": dry_run,
        "resume": resume,
        "executed": executed,
        "pending_count": len([x for x in _rank_tasks(state, task_ids=task_ids) if not x.get("completed")]),
        "state_path": state_path,
    }
    summary["paths"] = _write_upgrade_reports(root, summary)
    return summary
