import datetime as dt
from pathlib import Path

from overleaf_ce_mcp.template import init_paper_state_workspace
from overleaf_ce_mcp.workflow import run_paper_cycle


def test_run_paper_cycle_auto_weekly_friday(monkeypatch, tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo")
    called = {"loop": 0, "daily": 0, "weekly": 0}

    def _loop(**kwargs):
        called["loop"] += 1
        return {"ok": True, "round_count": 1}

    def _daily(**kwargs):
        called["daily"] += 1
        return {"ok": True, "date": kwargs["day"], "path": "/tmp/daily.md"}

    def _weekly(**kwargs):
        called["weekly"] += 1
        return {"ok": True, "week_tag": "2026-W09", "path": "/tmp/weekly.md"}

    monkeypatch.setattr("overleaf_ce_mcp.workflow.run_optimization_loop", _loop)
    monkeypatch.setattr("overleaf_ce_mcp.workflow.generate_daily_review", _daily)
    monkeypatch.setattr("overleaf_ce_mcp.workflow.generate_weekly_summary", _weekly)

    res = run_paper_cycle(
        project_dir=str(tmp_path),
        day="2026-02-27",
        weekly_mode="auto",
    )
    assert res["ok"] is True
    assert called["loop"] == 1
    assert called["daily"] == 1
    assert called["weekly"] == 1
    assert "weekly_summary" in res["executed_steps"]
    assert Path(res["paths"]["summary_json"]).exists()
    assert Path(res["paths"]["summary_markdown"]).exists()


def test_run_paper_cycle_auto_weekly_non_friday(monkeypatch, tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo")
    called = {"weekly": 0}

    monkeypatch.setattr("overleaf_ce_mcp.workflow.run_optimization_loop", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(
        "overleaf_ce_mcp.workflow.generate_daily_review",
        lambda **kwargs: {"ok": True, "date": kwargs["day"], "path": "/tmp/daily.md"},
    )

    def _weekly(**kwargs):
        called["weekly"] += 1
        return {"ok": True, "week_tag": "X", "path": "/tmp/weekly.md"}

    monkeypatch.setattr("overleaf_ce_mcp.workflow.generate_weekly_summary", _weekly)

    res = run_paper_cycle(
        project_dir=str(tmp_path),
        day="2026-03-01",
        weekly_mode="auto",
    )
    assert res["ok"] is True
    assert called["weekly"] == 0
    assert res["weekly_summary"] is None


def test_run_paper_cycle_invalid_weekly_mode(tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo")
    try:
        run_paper_cycle(project_dir=str(tmp_path), day=dt.date.today().isoformat(), weekly_mode="bad")
        assert False, "应当抛出异常"
    except ValueError as exc:
        assert "weekly_mode" in str(exc)

