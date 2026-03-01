import pytest

from overleaf_ce_mcp.deep_research import (
    generate_deep_research_prompt_set,
    synthesize_paper_strategy,
)


def test_generate_prompt_set_r1_count_and_meta():
    res = generate_deep_research_prompt_set(
        topic="offshore wave load prediction",
        known_data="6种工况，指标 RMSE/MAE/R2",
        writing_direction="强调 physics-informed 约束带来的泛化提升",
        round_stage="r1",
        num_prompts=6,
    )
    assert res["ok"] is True
    assert res["count"] == 6
    assert len(res["prompts"]) == 6
    assert res["prompts"][0]["id"] == "R1-P1-Landscape"
    assert res["prompts"][-1]["id"] == "R1-P6-JournalFit"
    assert res["meta"]["requested_prompts"] == 6
    assert res["meta"]["available_prompts"] == 6


def test_generate_prompt_set_r2_count_and_meta():
    res = generate_deep_research_prompt_set(
        topic="offshore wave load prediction",
        known_data="6种工况，指标 RMSE/MAE/R2",
        writing_direction="强调 physics-informed 约束带来的泛化提升",
        round_stage="r2",
        prior_findings="R1 指出需补充极端工况分析",
        num_prompts=6,
    )
    assert res["ok"] is True
    assert res["count"] == 6
    assert len(res["prompts"]) == 6
    assert res["prompts"][0]["id"] == "R2-P1-GapClosure"
    assert res["prompts"][-1]["id"] == "R2-P6-FinalNarrative"
    assert res["meta"]["requested_prompts"] == 6
    assert res["meta"]["available_prompts"] == 6


def test_synthesize_strategy_title_count_10():
    res = synthesize_paper_strategy(
        topic="offshore wave load prediction",
        candidate_title_count=10,
        improvement_modules=["physics constraint", "fusion block"],
    )
    titles = res["recommended_titles"]
    assert len(titles) == 10
    assert len(set(titles)) == 10


def test_synthesize_strategy_title_count_lower_bound():
    res = synthesize_paper_strategy(
        topic="offshore wave load prediction",
        candidate_title_count=1,
    )
    assert len(res["recommended_titles"]) == 3


def test_generate_prompt_set_invalid_stage():
    with pytest.raises(ValueError):
        generate_deep_research_prompt_set(
            topic="x",
            known_data="y",
            writing_direction="z",
            round_stage="r3",
        )
