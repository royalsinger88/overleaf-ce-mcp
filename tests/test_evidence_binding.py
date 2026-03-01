from pathlib import Path

from overleaf_ce_mcp.evidence_binding import run_manuscript_evidence_binding
from overleaf_ce_mcp.template import init_paper_state_workspace


def test_run_manuscript_evidence_binding_basic(tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo")
    (tmp_path / "main.tex").write_text(
        r"""
\section{Intro}

This paragraph has source 10.1234/demo.doi for traceability.

This paragraph has no source evidence.
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "paper_state" / "memory" / "claim_evidence.jsonl").write_text(
        '{"claim_id":"C001","claim":"demo claim","source_type":"doi","source":"10.1234/demo.doi","confidence":"high","status":"verified"}\n',
        encoding="utf-8",
    )

    res = run_manuscript_evidence_binding(project_dir=str(tmp_path), write_report=True)
    assert res["ok"] is True
    assert res["paragraph_total"] >= 2
    assert res["paragraph_covered"] >= 1
    assert Path(res["paths"]["report_json"]).exists()
    assert Path(res["paths"]["report_markdown"]).exists()
