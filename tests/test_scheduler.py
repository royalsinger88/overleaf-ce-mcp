from pathlib import Path

from overleaf_ce_mcp.scheduler import generate_scheduler_templates


def test_generate_scheduler_templates(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    project_dir = tmp_path / "paper"
    project_dir.mkdir(parents=True, exist_ok=True)

    res = generate_scheduler_templates(
        project_dir=str(project_dir),
        repo_dir=str(repo_dir),
        python_bin="/usr/bin/python3",
        daily_time="22:30",
    )
    assert res["ok"] is True
    paths = res["paths"]
    assert Path(paths["cron_daily"]).exists()
    assert Path(paths["cron_weekly"]).exists()
    assert Path(paths["systemd_daily_service"]).exists()
    assert Path(paths["systemd_daily_timer"]).exists()
    assert Path(paths["systemd_weekly_service"]).exists()
    assert Path(paths["systemd_weekly_timer"]).exists()

