from pathlib import Path

import pytest

from overleaf_ce_mcp.optimization_loop import run_optimization_loop
from overleaf_ce_mcp.template import init_paper_state_workspace


def test_run_optimization_loop_stops_on_no_gain(monkeypatch, tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo Topic")

    loop_cfg = tmp_path / "paper_state" / "inputs" / "loop.yaml"
    loop_cfg.write_text(
        "\n".join(
            [
                "topic: Demo Topic",
                "query: wave load prediction",
                "known_data: six sea states with RMSE/MAE/R2",
                "writing_direction: emphasize robust generalization",
                "max_rounds: 5",
                "patience: 1",
                "min_score_improvement: 0.05",
                "num_prompts: 6",
                "enable_journal_recommendation: true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_prompt_set(**kwargs):
        return {"ok": True, "count": 6, "prompts": []}

    def fake_related(**kwargs):
        return {
            "ok": True,
            "papers": [
                {
                    "title": "Paper A",
                    "doi": "10.1000/test-a",
                    "url": "https://example.com/a",
                },
                {
                    "title": "Paper B",
                    "arxiv_id": "2401.12345",
                    "url": "https://arxiv.org/abs/2401.12345",
                },
            ],
            "count": 2,
        }

    def fake_strategy(**kwargs):
        return {
            "ok": True,
            "recommended_titles": ["T1", "T2", "T3"],
            "innovation_points": ["I1", "I2"],
            "next_actions": ["A1", "A2"],
        }

    def fake_journal(**kwargs):
        return {
            "ok": True,
            "recommendations": [
                {"preset_key": "x", "score": 2.5, "matched_papers": 2},
            ],
        }

    monkeypatch.setattr("overleaf_ce_mcp.optimization_loop.generate_deep_research_prompt_set", fake_prompt_set)
    monkeypatch.setattr("overleaf_ce_mcp.optimization_loop.build_related_work_pack", fake_related)
    monkeypatch.setattr("overleaf_ce_mcp.optimization_loop.synthesize_paper_strategy", fake_strategy)
    monkeypatch.setattr("overleaf_ce_mcp.optimization_loop.recommend_target_journals", fake_journal)

    res = run_optimization_loop(project_dir=str(tmp_path))
    assert res["ok"] is True
    assert res["round_count"] == 2
    assert res["stop_reason"] == "stagnation_no_gain"

    summary_json = Path(res["paths"]["summary_json"])
    summary_md = Path(res["paths"]["summary_markdown"])
    daily = Path(res["paths"]["daily_review"])
    claim = Path(res["paths"]["claim_evidence"])

    assert summary_json.exists()
    assert summary_md.exists()
    assert daily.exists()
    assert claim.exists()
    assert "Round 1" in summary_md.read_text(encoding="utf-8")


def test_run_optimization_loop_with_direct_args(monkeypatch, tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo Topic")

    monkeypatch.setattr(
        "overleaf_ce_mcp.optimization_loop.generate_deep_research_prompt_set",
        lambda **kwargs: {"ok": True, "count": 3, "prompts": []},
    )
    monkeypatch.setattr(
        "overleaf_ce_mcp.optimization_loop.build_related_work_pack",
        lambda **kwargs: {"ok": True, "papers": [], "count": 0},
    )
    monkeypatch.setattr(
        "overleaf_ce_mcp.optimization_loop.synthesize_paper_strategy",
        lambda **kwargs: {
            "ok": True,
            "recommended_titles": ["T1", "T2", "T3"],
            "innovation_points": ["I1"],
            "next_actions": ["A1"],
        },
    )
    monkeypatch.setattr(
        "overleaf_ce_mcp.optimization_loop.recommend_target_journals",
        lambda **kwargs: {"ok": True, "recommendations": []},
    )

    res = run_optimization_loop(
        project_dir=str(tmp_path),
        topic="Wave Load Prediction",
        known_data="Known metrics",
        writing_direction="Focus on robust generalization",
        max_rounds=1,
        append_claim_evidence=False,
        write_daily_review=False,
    )
    assert res["ok"] is True
    assert res["round_count"] == 1
    assert res["stop_reason"] == "max_rounds_reached"


def test_run_optimization_loop_inner_cache_hits(monkeypatch, tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo Topic")
    called = {"related": 0, "journal": 0}

    monkeypatch.setattr(
        "overleaf_ce_mcp.optimization_loop.generate_deep_research_prompt_set",
        lambda **kwargs: {"ok": True, "count": 3, "prompts": []},
    )

    def _related(**kwargs):
        called["related"] += 1
        return {
            "ok": True,
            "papers": [{"title": "P1", "doi": "10.1/demo"}],
            "count": 1,
        }

    def _journal(**kwargs):
        called["journal"] += 1
        return {"ok": True, "recommendations": [{"score": 3.0}]}

    monkeypatch.setattr("overleaf_ce_mcp.optimization_loop.build_related_work_pack", _related)
    monkeypatch.setattr(
        "overleaf_ce_mcp.optimization_loop.synthesize_paper_strategy",
        lambda **kwargs: {
            "ok": True,
            "recommended_titles": ["T1"],
            "innovation_points": ["I1"],
            "next_actions": ["A1"],
        },
    )
    monkeypatch.setattr("overleaf_ce_mcp.optimization_loop.recommend_target_journals", _journal)

    res = run_optimization_loop(
        project_dir=str(tmp_path),
        topic="X",
        known_data="Y",
        writing_direction="Z",
        max_rounds=2,
        patience=3,
        use_cache=True,
        force_refresh=False,
    )
    assert res["ok"] is True
    assert called["related"] == 1
    assert called["journal"] == 1
    assert res["cache"]["related_work_hits"] >= 1
    assert res["cache"]["journal_hits"] >= 1


def test_run_optimization_loop_resume_from_checkpoint(monkeypatch, tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo Topic")
    state_file = tmp_path / "paper_state" / "memory" / "optimization_loop_state.json"
    calls = {"related": 0}

    monkeypatch.setattr(
        "overleaf_ce_mcp.optimization_loop.generate_deep_research_prompt_set",
        lambda **kwargs: {"ok": True, "count": 2, "prompts": []},
    )

    def _related_raise_on_second(**kwargs):
        calls["related"] += 1
        if calls["related"] >= 2:
            raise RuntimeError("network unstable")
        return {
            "ok": True,
            "papers": [{"title": "Paper A", "doi": "10.2/demo"}],
            "count": 1,
        }

    monkeypatch.setattr("overleaf_ce_mcp.optimization_loop.build_related_work_pack", _related_raise_on_second)
    monkeypatch.setattr(
        "overleaf_ce_mcp.optimization_loop.synthesize_paper_strategy",
        lambda **kwargs: {
            "ok": True,
            "recommended_titles": ["T1"],
            "innovation_points": ["I1"],
            "next_actions": ["A1"],
        },
    )
    monkeypatch.setattr(
        "overleaf_ce_mcp.optimization_loop.recommend_target_journals",
        lambda **kwargs: {"ok": True, "recommendations": []},
    )

    with pytest.raises(RuntimeError):
        run_optimization_loop(
            project_dir=str(tmp_path),
            topic="X",
            known_data="Y",
            writing_direction="Z",
            max_rounds=2,
            patience=3,
            use_cache=False,
            resume=True,
        )

    assert state_file.exists()

    monkeypatch.setattr(
        "overleaf_ce_mcp.optimization_loop.build_related_work_pack",
        lambda **kwargs: {"ok": True, "papers": [{"title": "Paper B", "doi": "10.3/demo"}], "count": 1},
    )
    res2 = run_optimization_loop(
        project_dir=str(tmp_path),
        topic="X",
        known_data="Y",
        writing_direction="Z",
        max_rounds=2,
        patience=3,
        use_cache=False,
        resume=True,
    )
    assert res2["ok"] is True
    assert res2["round_count"] == 2
    assert res2["resume"]["resumed_from_round"] == 1
