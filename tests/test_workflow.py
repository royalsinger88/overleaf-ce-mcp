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


def test_run_paper_cycle_auto_fill_from_inputs(monkeypatch, tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo")
    inputs = tmp_path / "paper_state" / "inputs"
    (inputs / "writing_brief.md").write_text(
        "# 写作初步思路\n\n"
        "## 研究问题\n- 解决极端海况下预测不稳定问题\n\n"
        "## 预期创新点\n- 引入物理一致性约束与双分支融合\n\n"
        "## 当前证据\n- 6种工况下 RMSE 平均下降 12.8%\n",
        encoding="utf-8",
    )
    (inputs / "submission_target.yaml").write_text(
        "submission:\n"
        '  primary_target_journal: "Ocean Engineering"\n',
        encoding="utf-8",
    )
    (inputs / "literature" / "seed_queries.yaml").write_text(
        "queries:\n"
        "  - name: baseline\n"
        '    text: "offshore wave load prediction physics-informed"\n'
        "    source: openreview\n",
        encoding="utf-8",
    )
    (inputs / "loop.yaml").write_text(
        'baseline_models: "LSTM baseline, Transformer baseline"\n'
        'improvement_modules: "Physics Constraint Module, Fusion Block"\n',
        encoding="utf-8",
    )
    (inputs / "experiments" / "registry.csv").write_text(
        "exp_id,purpose,split,metric_primary,status,owner,last_update,summary\n"
        "exp001,ablation,test,rmse,done,a,2026-03-01,ok\n",
        encoding="utf-8",
    )

    captured = {}

    def _loop(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "round_count": 1}

    monkeypatch.setattr("overleaf_ce_mcp.workflow.run_optimization_loop", _loop)
    monkeypatch.setattr(
        "overleaf_ce_mcp.workflow.generate_daily_review",
        lambda **kwargs: {"ok": True, "date": kwargs["day"], "path": "/tmp/daily.md"},
    )
    monkeypatch.setattr(
        "overleaf_ce_mcp.workflow.generate_weekly_summary",
        lambda **kwargs: {"ok": True, "week_tag": "2026-W09", "path": "/tmp/weekly.md"},
    )

    res = run_paper_cycle(
        project_dir=str(tmp_path),
        day="2026-03-01",
        weekly_mode="never",
    )
    assert res["ok"] is True
    assert "RMSE 平均下降" in str(captured.get("known_data") or "")
    assert "极端海况" in str(captured.get("writing_direction") or "")
    assert captured.get("target_journal") == "Ocean Engineering"
    assert captured.get("source") == "openreview"
    assert "offshore wave load" in str(captured.get("query") or "")
    assert captured.get("baseline_models") == ["LSTM baseline", "Transformer baseline"]
    assert captured.get("improvement_modules") == ["Physics Constraint Module", "Fusion Block"]
    assert res["auto_inputs"]["resolved"]["known_data"] is True
    assert Path(res["auto_inputs"]["paths"]["scan_json"]).exists()


def test_run_paper_cycle_write_missing_checklist(monkeypatch, tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo")
    monkeypatch.setattr("overleaf_ce_mcp.workflow.run_optimization_loop", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(
        "overleaf_ce_mcp.workflow.generate_daily_review",
        lambda **kwargs: {"ok": True, "date": kwargs["day"], "path": "/tmp/daily.md"},
    )

    res = run_paper_cycle(
        project_dir=str(tmp_path),
        day="2026-03-01",
        weekly_mode="never",
        run_loop=False,
        run_daily=False,
        write_missing_checklist=True,
    )
    assert res["ok"] is True
    miss = res["auto_inputs"]["missing_items"]
    assert isinstance(miss, list)
    assert len(miss) >= 1
    checklist = res["auto_inputs"]["paths"]["missing_checklist"]
    assert checklist is not None
    assert Path(checklist).exists()


def test_run_paper_cycle_strict_missing(tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo")
    try:
        run_paper_cycle(
            project_dir=str(tmp_path),
            day="2026-03-01",
            weekly_mode="never",
            run_loop=False,
            run_daily=False,
            strict_missing=True,
        )
        assert False, "应当抛出缺失素材异常"
    except ValueError as exc:
        assert "INPUT_MISSING.md" in str(exc)
