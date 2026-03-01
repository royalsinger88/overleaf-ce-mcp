from pathlib import Path

from overleaf_ce_mcp.template import init_paper_state_workspace
from overleaf_ce_mcp.upgrade_loop import list_upgrade_tasks, run_priority_upgrade_loop


def test_list_upgrade_tasks(tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo")
    res = list_upgrade_tasks(project_dir=str(tmp_path), include_completed=True)
    assert res["ok"] is True
    assert res["count"] >= 6
    assert res["tasks"][0]["id"] in ("paper_doctor", "run_and_sync_overleaf")


def test_run_priority_upgrade_loop_dry_run(tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo")
    res = run_priority_upgrade_loop(
        project_dir=str(tmp_path),
        max_tasks=3,
        dry_run=True,
        resume=True,
    )
    assert res["ok"] is True
    assert len(res["executed"]) >= 1
    assert Path(res["state_path"]).exists()
    assert Path(res["paths"]["summary_json"]).exists()


def test_run_priority_upgrade_loop_real_partial(tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo")
    # 仅跑前2项，避免触发外部同步依赖
    res = run_priority_upgrade_loop(
        project_dir=str(tmp_path),
        task_ids=["paper_doctor", "incremental_cache"],
        max_tasks=2,
        dry_run=False,
        resume=True,
    )
    assert res["ok"] is True
    done = [x["task_id"] for x in res["executed"] if x.get("ok")]
    assert "paper_doctor" in done
    assert "incremental_cache" in done

