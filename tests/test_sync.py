import os
from pathlib import Path

import pytest

from overleaf_ce_mcp import sync


def test_run_ols_uses_os_pathsep_and_dedup(monkeypatch):
    captured = {}

    monkeypatch.setattr(sync, "ensure_compat_patches", lambda: {"ok": True})
    monkeypatch.setattr(sync, "resolve_command", lambda cmd: "/usr/local/bin/ols")

    def fake_run_command(cmd, cwd=None, timeout=0, env=None):
        captured["cmd"] = cmd
        captured["env"] = env or {}
        return 0, "ok", ""

    monkeypatch.setattr(sync, "run_command", fake_run_command)

    code, out, err = sync.run_ols(["list"])
    assert code == 0
    assert out == "ok"
    assert err == ""
    assert captured["cmd"] == ["/usr/local/bin/ols", "list"]

    path_value = captured["env"]["PATH"]
    parts = [p for p in path_value.split(os.pathsep) if p]
    assert len(parts) == len(set(parts))
    assert str(Path(sync.sys.executable).parent) in parts


def test_ols_sync_scope_workspace_to_project_subdir(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    project = "paper-a"
    (workspace / project).mkdir(parents=True, exist_ok=True)

    captured = {}

    def fake_run_ols(args, cwd=None, timeout=1200, extra_env=None):
        captured["args"] = args
        captured["cwd"] = cwd
        captured["extra_env"] = extra_env or {}
        return 0, "ok", ""

    monkeypatch.setattr(sync, "run_ols", fake_run_ols)

    code, out, err = sync.ols_sync(
        workspace_path=str(workspace),
        project_name=project,
        mode="bidirectional",
    )
    assert code == 0
    assert out == "ok"
    assert err == ""
    assert "--name" in captured["args"]
    assert "--path" in captured["args"]
    path_index = captured["args"].index("--path")
    assert captured["args"][path_index + 1] == str(workspace / project)
    assert captured["cwd"] == str(workspace / project)


def test_ols_sync_invalid_mode_raises():
    with pytest.raises(ValueError):
        sync.ols_sync(mode="bad-mode")
