import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from overleaf_ce_mcp import server


def test_list_tools_contains_key_entries():
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert "generate_deep_research_prompt_set" in names
    assert "synthesize_paper_strategy" in names
    assert "init_model_diagram_pack" in names
    assert "list_journal_presets" in names
    assert "recommend_target_journals" in names
    assert "verify_reference" in names
    assert "letpub_search_journals" in names
    assert "letpub_get_journal_detail" in names
    assert "init_paper_state_workspace" in names
    assert "run_optimization_loop" in names
    assert "run_paper_cycle" in names
    assert "run_paper_doctor" in names
    assert "list_upgrade_tasks" in names
    assert "run_priority_upgrade_loop" in names
    assert "list_generic_priority_plan_templates" in names
    assert "init_generic_priority_plan" in names
    assert "list_generic_priority_tasks" in names
    assert "run_generic_priority_loop" in names
    assert "generate_daily_review" in names
    assert "generate_weekly_summary" in names
    assert "list_academic_source_capabilities" in names
    assert "fetch_paper_fulltext" in names
    assert "sync_zotero_paper_state" in names
    assert "search_openreview_papers" in names


def test_execute_tool_generate_deep_research_prompt_set():
    text = asyncio.run(
        server._execute_tool(
            "generate_deep_research_prompt_set",
            {
                "topic": "offshore wave load prediction",
                "known_data": "6种工况，RMSE/MAE/R2",
                "writing_direction": "强调物理约束泛化优势",
                "round_stage": "r1",
                "num_prompts": 6,
            },
        )
    )
    data = json.loads(text)
    assert data["ok"] is True
    assert data["count"] == 6


def test_call_tool_unknown_returns_error_payload():
    res = asyncio.run(server.call_tool("unknown_tool_name", {}))
    assert len(res) == 1
    payload = json.loads(res[0].text)
    assert payload["ok"] is False
    assert "未知工具" in payload["error"]


def test_execute_tool_list_journal_presets():
    text = asyncio.run(server._execute_tool("list_journal_presets", {}))
    data = json.loads(text)
    assert data["ok"] is True
    assert data["count"] >= 1


def test_execute_tool_init_paper_state_workspace():
    with TemporaryDirectory() as td:
        text = asyncio.run(
            server._execute_tool(
                "init_paper_state_workspace",
                {"project_dir": td},
            )
        )
        data = json.loads(text)
        assert data["ok"] is True
        root = Path(td) / "paper_state"
        assert root.exists()
        assert (root / "inputs" / "project.yaml").exists()
        assert (root / "review" / "daily" / "TEMPLATE.md").exists()


def test_execute_tool_run_optimization_loop(monkeypatch):
    def fake_runner(**kwargs):
        return {
            "ok": True,
            "round_count": 2,
            "stop_reason": "stagnation_no_gain",
            "paths": {"summary_json": "/tmp/summary.json"},
        }

    monkeypatch.setattr(server, "run_optimization_loop", fake_runner)
    text = asyncio.run(
        server._execute_tool(
            "run_optimization_loop",
            {
                "project_dir": "/tmp/paper-project",
                "topic": "offshore wave load prediction",
                "known_data": "RMSE/MAE",
                "writing_direction": "focus on reliability",
                "max_rounds": 3,
            },
        )
    )
    data = json.loads(text)
    assert data["ok"] is True
    assert data["round_count"] == 2


def test_execute_tool_list_academic_source_capabilities(monkeypatch):
    monkeypatch.setattr(
        server,
        "list_academic_source_capabilities",
        lambda **kwargs: {"ok": True, "count": 1, "sources": [{"key": "arxiv"}]},
    )
    text = asyncio.run(server._execute_tool("list_academic_source_capabilities", {}))
    data = json.loads(text)
    assert data["ok"] is True
    assert data["count"] == 1


def test_execute_tool_sync_zotero_paper_state(monkeypatch):
    monkeypatch.setattr(
        server,
        "sync_zotero_paper_state",
        lambda **kwargs: {"ok": True, "direction": "push", "dry_run": True},
    )
    text = asyncio.run(
        server._execute_tool(
            "sync_zotero_paper_state",
            {"project_dir": "/tmp/paper-project", "direction": "push", "dry_run": True},
        )
    )
    data = json.loads(text)
    assert data["ok"] is True
    assert data["direction"] == "push"


def test_execute_tool_search_openreview_papers(monkeypatch):
    class _DummyPaper:
        def to_dict(self):
            return {
                "source": "openreview",
                "paper_id": "abc",
                "title": "Demo",
                "abstract": "A",
                "authors": ["Alice"],
                "year": 2025,
                "venue": "ICLR.cc 2025",
                "url": "https://openreview.net/forum?id=abc",
                "pdf_url": "https://openreview.net/pdf?id=abc",
                "doi": None,
                "arxiv_id": None,
                "citation_count": None,
            }

    monkeypatch.setattr(
        server,
        "search_openreview_papers",
        lambda **kwargs: [_DummyPaper()],
    )
    text = asyncio.run(
        server._execute_tool(
            "search_openreview_papers",
            {"query": "diffusion", "venue": "ICLR", "year": 2025, "limit": 10},
        )
    )
    data = json.loads(text)
    assert data["ok"] is True
    assert data["count"] == 1


def test_execute_tool_generate_daily_review(monkeypatch):
    monkeypatch.setattr(
        server,
        "generate_daily_review",
        lambda **kwargs: {"ok": True, "date": "2026-03-01", "path": "/tmp/daily.md"},
    )
    text = asyncio.run(
        server._execute_tool(
            "generate_daily_review",
            {"project_dir": "/tmp/paper-project", "day": "2026-03-01"},
        )
    )
    data = json.loads(text)
    assert data["ok"] is True
    assert data["date"] == "2026-03-01"


def test_execute_tool_generate_weekly_summary(monkeypatch):
    monkeypatch.setattr(
        server,
        "generate_weekly_summary",
        lambda **kwargs: {"ok": True, "week_tag": "2026-W09", "path": "/tmp/weekly.md"},
    )
    text = asyncio.run(
        server._execute_tool(
            "generate_weekly_summary",
            {"project_dir": "/tmp/paper-project", "anchor_day": "2026-03-01"},
        )
    )
    data = json.loads(text)
    assert data["ok"] is True
    assert data["week_tag"] == "2026-W09"


def test_execute_tool_run_paper_cycle(monkeypatch):
    captured = {}

    def _runner(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "day": "2026-03-01",
            "weekly_mode": "auto",
            "executed_steps": ["optimization_loop", "daily_review"],
        }

    monkeypatch.setattr(
        server,
        "run_paper_cycle",
        _runner,
    )
    text = asyncio.run(
        server._execute_tool(
            "run_paper_cycle",
            {
                "project_dir": "/tmp/paper-project",
                "day": "2026-03-01",
                "auto_scan_inputs": True,
                "write_missing_checklist": True,
                "strict_missing": False,
            },
        )
    )
    data = json.loads(text)
    assert data["ok"] is True
    assert "daily_review" in data["executed_steps"]
    assert captured["auto_scan_inputs"] is True
    assert captured["write_missing_checklist"] is True
    assert captured["strict_missing"] is False


def test_execute_tool_run_paper_doctor(monkeypatch):
    monkeypatch.setattr(
        server,
        "run_paper_doctor",
        lambda **kwargs: {"ok": True, "score": 0.9, "summary": {"high": 0, "medium": 1, "low": 1}},
    )
    text = asyncio.run(
        server._execute_tool(
            "run_paper_doctor",
            {"project_dir": "/tmp/paper-project"},
        )
    )
    data = json.loads(text)
    assert data["ok"] is True
    assert data["score"] == 0.9


def test_execute_tool_list_upgrade_tasks(monkeypatch):
    monkeypatch.setattr(
        server,
        "list_upgrade_tasks",
        lambda **kwargs: {"ok": True, "count": 2, "tasks": [{"id": "paper_doctor"}, {"id": "run_and_sync_overleaf"}]},
    )
    text = asyncio.run(
        server._execute_tool(
            "list_upgrade_tasks",
            {"project_dir": "/tmp/paper-project"},
        )
    )
    data = json.loads(text)
    assert data["ok"] is True
    assert data["count"] == 2


def test_execute_tool_run_priority_upgrade_loop(monkeypatch):
    monkeypatch.setattr(
        server,
        "run_priority_upgrade_loop",
        lambda **kwargs: {"ok": True, "executed": [{"task_id": "paper_doctor", "ok": True}]},
    )
    text = asyncio.run(
        server._execute_tool(
            "run_priority_upgrade_loop",
            {"project_dir": "/tmp/paper-project", "max_tasks": 2, "dry_run": True},
        )
    )
    data = json.loads(text)
    assert data["ok"] is True
    assert data["executed"][0]["task_id"] == "paper_doctor"


def test_execute_tool_list_generic_priority_tasks(monkeypatch):
    monkeypatch.setattr(
        server,
        "list_generic_priority_tasks",
        lambda **kwargs: {"ok": True, "count": 1, "tasks": [{"id": "t1"}]},
    )
    text = asyncio.run(
        server._execute_tool(
            "list_generic_priority_tasks",
            {"workspace_dir": "/tmp/ws", "plan_path": "plan.json"},
        )
    )
    data = json.loads(text)
    assert data["ok"] is True
    assert data["count"] == 1


def test_execute_tool_list_generic_priority_plan_templates(monkeypatch):
    monkeypatch.setattr(
        server,
        "list_generic_priority_plan_templates",
        lambda **kwargs: {"ok": True, "count": 2, "templates": [{"name": "a"}, {"name": "b"}]},
    )
    text = asyncio.run(
        server._execute_tool(
            "list_generic_priority_plan_templates",
            {},
        )
    )
    data = json.loads(text)
    assert data["ok"] is True
    assert data["count"] == 2


def test_execute_tool_init_generic_priority_plan(monkeypatch):
    monkeypatch.setattr(
        server,
        "init_generic_priority_plan",
        lambda **kwargs: {"ok": True, "plan_path": "/tmp/ws/plan.json"},
    )
    text = asyncio.run(
        server._execute_tool(
            "init_generic_priority_plan",
            {"workspace_dir": "/tmp/ws", "template_name": "dev-feature-cycle"},
        )
    )
    data = json.loads(text)
    assert data["ok"] is True
    assert data["plan_path"].endswith("plan.json")


def test_execute_tool_run_generic_priority_loop(monkeypatch):
    captured = {}

    def _runner(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "executed": [{"task_id": "t1", "ok": True}]}

    monkeypatch.setattr(
        server,
        "run_generic_priority_loop",
        _runner,
    )
    text = asyncio.run(
        server._execute_tool(
            "run_generic_priority_loop",
            {"workspace_dir": "/tmp/ws", "plan_path": "plan.json", "dry_run": True},
        )
    )
    data = json.loads(text)
    assert data["ok"] is True
    assert data["executed"][0]["task_id"] == "t1"
    assert captured["plan_path"] == "plan.json"


def test_execute_tool_run_generic_priority_loop_with_task_text(monkeypatch):
    captured = {}

    def _runner(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "executed": [{"task_id": "task_001", "ok": True}]}

    monkeypatch.setattr(server, "run_generic_priority_loop", _runner)
    text = asyncio.run(
        server._execute_tool(
            "run_generic_priority_loop",
            {
                "workspace_dir": "/tmp/ws",
                "task_text": "改进A\n改进B",
                "default_action": "noop",
                "dry_run": True,
            },
        )
    )
    data = json.loads(text)
    assert data["ok"] is True
    assert captured["task_text"] == "改进A\n改进B"
    assert captured["plan_path"] is None
