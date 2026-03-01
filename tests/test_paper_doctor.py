from pathlib import Path

from overleaf_ce_mcp.paper_doctor import run_paper_doctor
from overleaf_ce_mcp.template import init_paper_state_workspace


def test_run_paper_doctor_detects_missing(tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo")
    # 人为制造缺失
    (tmp_path / "paper_state" / "inputs" / "writing_brief.md").write_text("", encoding="utf-8")
    res = run_paper_doctor(project_dir=str(tmp_path), write_report=True)
    assert res["ok"] is False
    assert res["summary"]["high"] >= 1
    assert Path(res["paths"]["report_json"]).exists()
    assert Path(res["paths"]["report_markdown"]).exists()


def test_run_paper_doctor_pass_basic(tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo")
    # 填充最小可用内容
    (tmp_path / "paper_state" / "inputs" / "writing_brief.md").write_text(
        "# 写作初步思路\n\n## 研究问题\n- A\n\n## 预期创新点\n- B\n\n## 当前证据\n- C\n",
        encoding="utf-8",
    )
    res = run_paper_doctor(project_dir=str(tmp_path), write_report=False)
    assert "summary" in res
    assert res["summary"]["high"] == 0

