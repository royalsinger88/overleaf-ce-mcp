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
