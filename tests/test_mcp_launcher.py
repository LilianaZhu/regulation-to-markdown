from __future__ import annotations

import os
from types import SimpleNamespace

from scripts import mcp_launcher


def test_runtime_install_does_not_expose_mineru_token_to_subprocesses(
    tmp_path, monkeypatch
):
    root = tmp_path / "plugin"
    data = tmp_path / "data"
    root.mkdir()
    data.mkdir()
    monkeypatch.setenv("MINERU_API_TOKEN", "mineru-secret")
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_MINERU_API_TOKEN", "option-secret")

    observed: dict[str, dict[str, str]] = {}

    class FakeEnvBuilder:
        def __init__(self, **_kwargs):
            pass

        def create(self, runtime):
            observed["venv"] = dict(os.environ)
            runtime_python = mcp_launcher._runtime_python(runtime)
            runtime_python.parent.mkdir(parents=True, exist_ok=True)
            runtime_python.touch()

    def fake_run(_command, **kwargs):
        observed["pip"] = kwargs["env"]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(mcp_launcher.venv, "EnvBuilder", FakeEnvBuilder)
    monkeypatch.setattr(mcp_launcher.subprocess, "run", fake_run)

    runtime_python = mcp_launcher._install(root, data)

    assert runtime_python.is_file()
    for environment in observed.values():
        assert "MINERU_API_TOKEN" not in environment
        assert "CLAUDE_PLUGIN_OPTION_MINERU_API_TOKEN" not in environment
    assert os.environ["MINERU_API_TOKEN"] == "mineru-secret"
    assert os.environ["CLAUDE_PLUGIN_OPTION_MINERU_API_TOKEN"] == "option-secret"
    bootstrap_log = (data / "bootstrap.log").read_text(encoding="utf-8")
    assert "mineru-secret" not in bootstrap_log
    assert "option-secret" not in bootstrap_log
