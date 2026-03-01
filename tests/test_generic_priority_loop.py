import json
from pathlib import Path

from overleaf_ce_mcp.generic_priority_loop import (
    init_generic_priority_plan,
    list_generic_priority_plan_templates,
    list_generic_priority_tasks,
    run_generic_priority_loop,
)


def _write_plan(path: Path) -> None:
    plan = {
        "tasks": [
            {
                "id": "t1",
                "title": "First",
                "impact": 10,
                "effort": 2,
                "dependencies": [],
                "action": {"type": "noop"},
            },
            {
                "id": "t2",
                "title": "Second",
                "impact": 7,
                "effort": 3,
                "dependencies": ["t1"],
                "action": {"type": "shell", "cmd": "echo ok > marker.txt"},
            },
        ]
    }
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")


def test_list_generic_priority_tasks(tmp_path):
    plan = tmp_path / "plan.json"
    _write_plan(plan)
    res = list_generic_priority_tasks(
        workspace_dir=str(tmp_path),
        plan_path=str(plan),
        include_completed=True,
    )
    assert res["ok"] is True
    assert res["count"] == 2
    assert res["tasks"][0]["id"] == "t1"


def test_list_generic_priority_plan_templates():
    res = list_generic_priority_plan_templates()
    assert res["ok"] is True
    assert res["count"] >= 4
    names = {x["name"] for x in res["templates"]}
    assert "dev-feature-cycle" in names


def test_init_generic_priority_plan(tmp_path):
    res = init_generic_priority_plan(
        workspace_dir=str(tmp_path),
        template_name="dev-feature-cycle",
        output_path="my-plan.json",
        force=False,
    )
    assert res["ok"] is True
    p = Path(res["plan_path"])
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert '"tasks"' in text


def test_run_generic_priority_loop_dry_run(tmp_path):
    plan = tmp_path / "plan.json"
    _write_plan(plan)
    res = run_generic_priority_loop(
        workspace_dir=str(tmp_path),
        plan_path=str(plan),
        dry_run=True,
        resume=True,
    )
    assert res["ok"] is True
    assert len(res["executed"]) >= 1
    assert Path(res["state_path"]).exists()
    assert Path(res["paths"]["run_json"]).exists()


def test_run_generic_priority_loop_shell(tmp_path):
    plan = tmp_path / "plan.json"
    _write_plan(plan)

    # 先跑一次 noop，确保依赖完成
    res1 = run_generic_priority_loop(
        workspace_dir=str(tmp_path),
        plan_path=str(plan),
        max_tasks=1,
        dry_run=False,
        resume=True,
        allow_shell=False,
    )
    assert res1["ok"] is True

    # 再跑 shell 任务
    res2 = run_generic_priority_loop(
        workspace_dir=str(tmp_path),
        plan_path=str(plan),
        max_tasks=2,
        dry_run=False,
        resume=True,
        allow_shell=True,
    )
    assert any(x.get("task_id") == "t2" and x.get("ok") for x in res2["executed"])
    assert (tmp_path / "marker.txt").exists()
