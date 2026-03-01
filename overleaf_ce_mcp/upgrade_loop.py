"""按优先级循环执行工程改造任务（upgrade loop）。"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paper_doctor import run_paper_doctor
from .sync import command_exists, ols_sync, run_command
from .upload import (
    health_check_project,
    package_project_for_upload,
    upload_zip_as_new_project,
)
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


def _run_evidence_binding(project_root: Path) -> Dict[str, Any]:
    claim_file = project_root / "paper_state" / "memory" / "claim_evidence.jsonl"
    tex_files: List[Path] = []
    main_tex = project_root / "main.tex"
    if main_tex.exists():
        tex_files.append(main_tex)
    sec_dir = project_root / "sections"
    if sec_dir.exists() and sec_dir.is_dir():
        tex_files.extend(sorted(sec_dir.glob("*.tex")))

    claims: List[Dict[str, str]] = []
    if claim_file.exists():
        for raw in claim_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            claims.append(
                {
                    "claim": str(obj.get("claim") or "").strip(),
                    "source": str(obj.get("source") or "").strip(),
                }
            )

    claim_keywords: List[str] = []
    for c in claims:
        for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", c["claim"]):
            t = token.strip().lower()
            if len(t) >= 4:
                claim_keywords.append(t)
    claim_keywords = sorted(set(claim_keywords))

    paragraph_total = 0
    paragraph_covered = 0
    file_rows: List[Dict[str, Any]] = []

    for tf in tex_files:
        text = tf.read_text(encoding="utf-8")
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
        para_rows = []
        for idx, b in enumerate(blocks, start=1):
            if b.startswith("%"):
                continue
            if b.startswith("\\section") or b.startswith("\\subsection") or b.startswith("\\begin"):
                continue
            paragraph_total += 1
            low = b.lower()
            covered = False
            hit_source = None
            for c in claims:
                src = c["source"]
                if src and src.lower() in low:
                    covered = True
                    hit_source = src
                    break
            if not covered and claim_keywords:
                hits = 0
                for kw in claim_keywords:
                    if kw in low:
                        hits += 1
                    if hits >= 2:
                        covered = True
                        hit_source = "keyword-match"
                        break
            if covered:
                paragraph_covered += 1
            para_rows.append(
                {
                    "paragraph_index": idx,
                    "covered": covered,
                    "hit": hit_source,
                    "preview": b[:160].replace("\n", " "),
                }
            )
        file_rows.append(
            {
                "file": str(tf),
                "paragraph_count": len(para_rows),
                "covered_count": sum(1 for x in para_rows if x["covered"]),
                "coverage_ratio": round(
                    (sum(1 for x in para_rows if x["covered"]) / len(para_rows)),
                    4,
                )
                if para_rows
                else 0.0,
                "paragraphs": para_rows[:40],
            }
        )

    ratio = round((paragraph_covered / paragraph_total), 4) if paragraph_total else 0.0
    out_dir = project_root / "paper_state" / "outputs" / "evidence_binding"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    jp = out_dir / f"coverage_{ts}.json"
    mp = out_dir / f"coverage_{ts}.md"
    payload = {
        "ok": True,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "paragraph_total": paragraph_total,
        "paragraph_covered": paragraph_covered,
        "coverage_ratio": ratio,
        "files": file_rows,
    }
    jp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Manuscript Evidence Coverage",
        "",
        f"- 段落总数：{paragraph_total}",
        f"- 已覆盖段落：{paragraph_covered}",
        f"- 覆盖率：{ratio}",
        "",
        "## 文件覆盖率",
    ]
    for fr in file_rows:
        lines.append(
            f"- {fr['file']} | paragraphs={fr['paragraph_count']} | "
            f"covered={fr['covered_count']} | ratio={fr['coverage_ratio']}"
        )
    mp.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    payload["paths"] = {"report_json": str(jp), "report_markdown": str(mp)}
    return payload


def _setup_incremental_cache(project_root: Path) -> Dict[str, Any]:
    cache_dir = project_root / "paper_state" / "cache" / "paper_cycle"
    cache_dir.mkdir(parents=True, exist_ok=True)
    policy = project_root / "paper_state" / "cache" / "policy.yaml"
    if not policy.exists():
        policy.write_text(
            "cache:\n"
            "  paper_cycle_enabled: true\n"
            "  default_ttl_hours: 24\n"
            "  force_refresh: false\n",
            encoding="utf-8",
        )
    readme = project_root / "paper_state" / "cache" / "README.md"
    if not readme.exists():
        readme.write_text(
            "# 增量缓存\n\n"
            "- `paper_cycle` 缓存目录：`paper_state/cache/paper_cycle`\n"
            "- 可通过 `run_paper_cycle(use_cache=true|false, force_refresh=true|false)` 控制。\n",
            encoding="utf-8",
        )
    return {"ok": True, "cache_dir": str(cache_dir), "policy_file": str(policy), "readme": str(readme)}


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
    )

    local_compile = {"ok": False, "skipped": True, "reason": "main.tex 或 latexmk 不可用"}
    main_tex = project_root / "main.tex"
    if main_tex.exists() and command_exists("latexmk"):
        code, out, err = run_command(
            ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
            cwd=str(project_root),
            timeout=1800,
        )
        local_compile = {
            "ok": code == 0 and (project_root / "main.pdf").exists(),
            "skipped": False,
            "exit_code": code,
            "stdout_tail": out[-1200:],
            "stderr_tail": err[-1200:],
        }

    sync_mode_norm = str(sync_mode or "none").strip().lower()
    if sync_mode_norm not in ("none", "sync", "upload"):
        raise ValueError("sync_mode 仅支持 none/sync/upload")

    remote: Dict[str, Any] = {"mode": sync_mode_norm, "ok": True, "actions": []}
    if sync_mode_norm == "none":
        remote["actions"].append("skip_remote_sync")
    elif sync_mode_norm == "sync":
        if not (ce_url and store_path and project_name):
            remote["ok"] = False
            remote["error"] = "sync 模式需提供 ce_url/store_path/project_name"
        else:
            code, out, err = ols_sync(
                workspace_path=str(project_root),
                project_name=project_name,
                ce_url=ce_url,
                store_path=store_path,
                mode="bidirectional",
                delete_policy="i",
                verbose=False,
            )
            remote["sync"] = {"ok": code == 0, "exit_code": code, "stdout_tail": out[-1200:], "stderr_tail": err[-1200:]}
            if code == 0:
                remote["health"] = health_check_project(
                    ce_url=ce_url,
                    store_path=store_path,
                    project_name=project_name,
                    compile_check=True,
                )
            remote["ok"] = bool(remote.get("sync", {}).get("ok"))
    elif sync_mode_norm == "upload":
        if not (ce_url and store_path):
            remote["ok"] = False
            remote["error"] = "upload 模式需提供 ce_url/store_path"
        else:
            pack = package_project_for_upload(project_dir=str(project_root))
            up = upload_zip_as_new_project(ce_url=ce_url, store_path=store_path, zip_path=str(pack["zip_path"]))
            remote["package"] = pack
            remote["upload"] = up
            remote["ok"] = bool(up.get("ok"))

    return {"ok": bool(cycle.get("ok")) and bool(local_compile.get("ok") or local_compile.get("skipped")), "cycle": cycle, "local_compile": local_compile, "remote": remote}


def _generate_scheduler_templates(project_root: Path) -> Dict[str, Any]:
    auto_dir = project_root / "paper_state" / "automation"
    auto_dir.mkdir(parents=True, exist_ok=True)
    cron = auto_dir / "paper_cycle.cron.example"
    service = auto_dir / "paper-cycle.service"
    timer = auto_dir / "paper-cycle.timer"
    cron.write_text(
        "# 每日 23:10 跑一次 paper_cycle\n"
        "10 23 * * * cd /path/to/overleaf-ce-mcp && "
        "python -c \"from overleaf_ce_mcp.workflow import run_paper_cycle; "
        "run_paper_cycle(project_dir='/path/to/project', weekly_mode='auto')\"\n",
        encoding="utf-8",
    )
    service.write_text(
        "[Unit]\n"
        "Description=Paper Cycle Automation\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        "WorkingDirectory=/path/to/overleaf-ce-mcp\n"
        "ExecStart=/usr/bin/python -c \"from overleaf_ce_mcp.workflow import run_paper_cycle; "
        "run_paper_cycle(project_dir='/path/to/project', weekly_mode='auto')\"\n",
        encoding="utf-8",
    )
    timer.write_text(
        "[Unit]\n"
        "Description=Run Paper Cycle Daily\n\n"
        "[Timer]\n"
        "OnCalendar=*-*-* 23:10:00\n"
        "Persistent=true\n\n"
        "[Install]\n"
        "WantedBy=timers.target\n",
        encoding="utf-8",
    )
    return {"ok": True, "cron_template": str(cron), "systemd_service": str(service), "systemd_timer": str(timer)}


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
                    result = _run_evidence_binding(root)
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
                    result = _generate_scheduler_templates(root)
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

