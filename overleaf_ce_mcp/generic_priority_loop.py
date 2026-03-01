"""通用优先级循环执行器（与论文场景解耦）。"""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def _loop_root(workspace_root: Path) -> Path:
    p = workspace_root / ".codex" / "priority-loop"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _state_path(workspace_root: Path) -> Path:
    return _loop_root(workspace_root) / "state.json"


def _load_state(workspace_root: Path) -> Dict[str, Any]:
    fp = _state_path(workspace_root)
    if not fp.exists():
        return {"completed": {}, "history": []}
    try:
        obj = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {"completed": {}, "history": []}
    if not isinstance(obj, dict):
        return {"completed": {}, "history": []}
    return {
        "completed": obj.get("completed") if isinstance(obj.get("completed"), dict) else {},
        "history": obj.get("history") if isinstance(obj.get("history"), list) else [],
    }


def _save_state(workspace_root: Path, state: Dict[str, Any]) -> str:
    fp = _state_path(workspace_root)
    state["updated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    fp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(fp)


def _load_plan(plan_path: Path) -> Dict[str, Any]:
    if not plan_path.exists() or not plan_path.is_file():
        raise ValueError(f"plan_path 不存在: {plan_path}")
    try:
        obj = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError("当前仅支持 JSON 计划文件") from exc
    if not isinstance(obj, dict):
        raise ValueError("计划文件格式错误，应为 JSON object")
    tasks = obj.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("计划文件需包含非空 tasks 数组")
    return obj


def _normalize_task(task: Dict[str, Any]) -> Dict[str, Any]:
    tid = str(task.get("id") or "").strip()
    if not tid:
        raise ValueError("任务缺少 id")
    title = str(task.get("title") or tid).strip()
    impact = int(task.get("impact", 5))
    effort = int(task.get("effort", 3))
    deps = task.get("dependencies")
    if not isinstance(deps, list):
        deps = []
    deps_clean = [str(x).strip() for x in deps if str(x).strip()]
    action = task.get("action")
    if not isinstance(action, dict):
        action = {"type": "noop"}
    atype = str(action.get("type") or "noop").strip().lower()
    out = {
        "id": tid,
        "title": title,
        "impact": max(1, min(10, impact)),
        "effort": max(1, min(10, effort)),
        "dependencies": deps_clean,
        "action": action,
        "action_type": atype,
    }
    return out


def _priority_score(task: Dict[str, Any], completed: Dict[str, Any]) -> float:
    dep_penalty = 0.0
    for dep in task.get("dependencies") or []:
        if not bool(completed.get(dep, {}).get("ok")):
            dep_penalty += 2.0
    return round((task["impact"] * 2.0) - (task["effort"] * 1.0) - dep_penalty, 2)


def _rank_tasks(tasks: List[Dict[str, Any]], completed: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for t in tasks:
        row = dict(t)
        row["priority_score"] = _priority_score(row, completed)
        row["completed"] = bool(completed.get(row["id"], {}).get("ok"))
        out.append(row)
    out.sort(key=lambda x: (x["priority_score"], x["impact"]), reverse=True)
    return out


def _run_shell(cmd: str, cwd: Path, timeout: int) -> Dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
        shell=True,
    )
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


def _write_run_reports(workspace_root: Path, payload: Dict[str, Any]) -> Dict[str, str]:
    runs = _loop_root(workspace_root) / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    jp = runs / f"run_{ts}.json"
    mp = runs / f"run_{ts}.md"
    latest_json = runs / "latest.json"
    latest_md = runs / "latest.md"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    jp.write_text(text, encoding="utf-8")
    latest_json.write_text(text, encoding="utf-8")

    lines = [
        "# Generic Priority Loop Run",
        "",
        f"- 执行时间（UTC）：{payload.get('executed_at')}",
        f"- dry_run：{payload.get('dry_run')}",
        f"- 执行任务数：{len(payload.get('executed') or [])}",
        "",
        "## 执行结果",
    ]
    for r in payload.get("executed") or []:
        lines.append(
            f"- {r.get('task_id')} | status={r.get('status')} | ok={r.get('ok')} | score={r.get('priority_score')}"
        )
    if not (payload.get("executed") or []):
        lines.append("- [无]")
    md_text = "\n".join(lines).rstrip() + "\n"
    mp.write_text(md_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    return {
        "run_json": str(jp),
        "run_markdown": str(mp),
        "latest_json": str(latest_json),
        "latest_markdown": str(latest_md),
    }


def list_generic_priority_tasks(
    workspace_dir: str,
    plan_path: str,
    include_completed: bool = True,
) -> Dict[str, Any]:
    root = Path(workspace_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"workspace_dir 不是有效目录: {root}")
    pp = Path(plan_path).expanduser()
    if not pp.is_absolute():
        pp = (root / pp).resolve()
    plan = _load_plan(pp)
    raw_tasks = [_normalize_task(x) for x in plan["tasks"]]
    state = _load_state(root)
    completed = state.get("completed") if isinstance(state.get("completed"), dict) else {}
    ranked = _rank_tasks(raw_tasks, completed=completed)
    if not include_completed:
        ranked = [x for x in ranked if not x["completed"]]
    return {
        "ok": True,
        "workspace_dir": str(root),
        "plan_path": str(pp),
        "count": len(ranked),
        "tasks": ranked,
    }


def run_generic_priority_loop(
    workspace_dir: str,
    plan_path: str,
    max_tasks: int = 10,
    dry_run: bool = False,
    continue_on_error: bool = True,
    resume: bool = True,
    allow_shell: bool = False,
    default_timeout_sec: int = 1800,
) -> Dict[str, Any]:
    root = Path(workspace_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"workspace_dir 不是有效目录: {root}")
    pp = Path(plan_path).expanduser()
    if not pp.is_absolute():
        pp = (root / pp).resolve()
    plan = _load_plan(pp)
    raw_tasks = [_normalize_task(x) for x in plan["tasks"]]

    state = _load_state(root) if resume else {"completed": {}, "history": []}
    completed = state.get("completed") if isinstance(state.get("completed"), dict) else {}
    history = state.get("history") if isinstance(state.get("history"), list) else []

    ranked = _rank_tasks(raw_tasks, completed=completed)
    todo = [x for x in ranked if not x["completed"]]
    todo = todo[: max(1, int(max_tasks))]

    executed: List[Dict[str, Any]] = []
    for task in todo:
        tid = task["id"]
        row: Dict[str, Any] = {
            "task_id": tid,
            "title": task["title"],
            "priority_score": task["priority_score"],
            "started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        deps = task.get("dependencies") or []
        unmet = [d for d in deps if not bool(completed.get(d, {}).get("ok"))]
        if unmet:
            row["ok"] = False
            row["status"] = "blocked"
            row["error"] = f"依赖未完成: {', '.join(unmet)}"
            row["finished_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
            executed.append(row)
            history.append(row)
            continue
        try:
            if dry_run:
                result = {"ok": True, "dry_run": True}
                row["ok"] = True
                row["status"] = "planned"
                row["result"] = result
            else:
                atype = task["action_type"]
                action = task["action"]
                if atype == "noop":
                    result = {"ok": True, "note": "noop task"}
                elif atype == "shell":
                    if not allow_shell:
                        raise ValueError("该任务为 shell 类型，需显式传 allow_shell=true")
                    cmd = str(action.get("cmd") or "").strip()
                    if not cmd:
                        raise ValueError("shell 任务缺少 action.cmd")
                    cwd_raw = str(action.get("cwd") or ".")
                    cwd = (root / cwd_raw).resolve() if not Path(cwd_raw).is_absolute() else Path(cwd_raw)
                    timeout = int(action.get("timeout_sec") or default_timeout_sec)
                    result = _run_shell(cmd=cmd, cwd=cwd, timeout=max(1, timeout))
                else:
                    raise ValueError(f"不支持的 action.type: {atype}")

                row["ok"] = bool(result.get("ok"))
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
    state["history"] = history[-500:]
    state_path = _save_state(root, state)

    pending = [x for x in _rank_tasks(raw_tasks, completed=completed) if not x["completed"]]
    payload: Dict[str, Any] = {
        "ok": all(bool(x.get("ok")) for x in executed if x.get("status") not in ("blocked",)) if executed else True,
        "workspace_dir": str(root),
        "plan_path": str(pp),
        "executed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "dry_run": dry_run,
        "resume": resume,
        "allow_shell": allow_shell,
        "executed": executed,
        "pending_count": len(pending),
        "state_path": state_path,
    }
    payload["paths"] = _write_run_reports(root, payload)
    return payload

