import asyncio
import json

from overleaf_ce_mcp import server


def test_list_tools_contains_key_entries():
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert "generate_deep_research_prompt_set" in names
    assert "synthesize_paper_strategy" in names
    assert "init_model_diagram_pack" in names


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
