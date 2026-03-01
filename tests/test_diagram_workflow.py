import json

import pytest

from overleaf_ce_mcp.diagram_workflow import init_model_diagram_pack


def test_init_model_diagram_pack_supports_large_module_count(tmp_path):
    modules = [f"Module {i}" for i in range(1, 31)]
    res = init_model_diagram_pack(
        project_dir=str(tmp_path),
        model_name="BigNet",
        modules=modules,
        truth_priority="mermaid",
        force=True,
    )

    assert res["ok"] is True
    out_dir = tmp_path / "figures" / "model-diagram"
    truth = (out_dir / "01-topology-truth.mmd").read_text(encoding="utf-8")
    assert 'N30["Module 30"]' in truth
    assert "N29 --> N30" in truth


def test_init_model_diagram_pack_drawio_lock(tmp_path):
    drawio_file = tmp_path / "truth.drawio"
    drawio_file.write_text("<mxfile><diagram>ok</diagram></mxfile>\n", encoding="utf-8")

    res = init_model_diagram_pack(
        project_dir=str(tmp_path),
        model_name="BigNet",
        drawio_file_path=str(drawio_file),
        truth_priority="drawio",
        force=True,
    )
    assert res["ok"] is True
    assert res["truth_mode"] == "drawio"

    out_dir = tmp_path / "figures" / "model-diagram"
    lock_path = out_dir / "01-topology-lock.json"
    assert lock_path.exists()
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    assert lock["truth_mode"] == "drawio"
    assert lock["sha256"]


def test_init_model_diagram_pack_drawio_without_file_raises(tmp_path):
    with pytest.raises(ValueError):
        init_model_diagram_pack(
            project_dir=str(tmp_path),
            model_name="BigNet",
            truth_priority="drawio",
        )
