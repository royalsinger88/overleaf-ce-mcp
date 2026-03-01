from pathlib import Path

from overleaf_ce_mcp.template import init_paper_state_workspace, init_template_project


def test_init_paper_state_workspace_creates_expected_files(tmp_path):
    res = init_paper_state_workspace(
        project_dir=str(tmp_path),
        title="Demo Title",
        authors="Alice, Bob",
        corresponding_email="alice@example.com",
        keywords="ocean, pinn",
    )
    assert "paper_state/inputs/project.yaml" in res["created_files"]
    assert "paper_state/inputs/literature/seed_queries.yaml" in res["created_files"]
    assert "paper_state/review/daily/TEMPLATE.md" in res["created_files"]
    assert "paper_state/review/weekly/TEMPLATE.md" in res["created_files"]
    assert "paper_state/memory/claim_evidence.jsonl" in res["created_files"]

    p = Path(tmp_path) / "paper_state" / "inputs" / "project.yaml"
    text = p.read_text(encoding="utf-8")
    assert "Demo Title" in text
    assert "alice@example.com" in text


def test_init_paper_state_workspace_skip_existing_when_not_force(tmp_path):
    res1 = init_paper_state_workspace(project_dir=str(tmp_path))
    assert len(res1["created_files"]) > 0
    res2 = init_paper_state_workspace(project_dir=str(tmp_path), force=False)
    assert len(res2["created_files"]) == 0
    assert len(res2["skipped_files"]) > 0


def test_init_template_project_auto_create_paper_state(tmp_path):
    target = tmp_path / "paper_project"
    res = init_template_project(
        template_name="ocean-engineering-oa",
        target_dir=str(target),
        init_paper_state=True,
    )
    assert res["paper_state"] is not None
    assert (target / "paper_state" / "inputs" / "project.yaml").exists()
