from __future__ import annotations

import os
from pathlib import Path
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
    monkeypatch.setenv("REG2MD_PLUGIN_DATA", "${CLAUDE_PLUGIN_DATA}")

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
    assert "REG2MD_PLUGIN_DATA" not in observed["pip"]
    assert os.environ["MINERU_API_TOKEN"] == "mineru-secret"
    assert os.environ["CLAUDE_PLUGIN_OPTION_MINERU_API_TOKEN"] == "option-secret"
    bootstrap_log = (data / "bootstrap.log").read_text(encoding="utf-8")
    assert "mineru-secret" not in bootstrap_log
    assert "option-secret" not in bootstrap_log


def test_plugin_paths_ignore_unresolved_host_placeholders(tmp_path, monkeypatch):
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    (plugin_root / "pyproject.toml").write_text(
        "[project]\nname='x'\n", encoding="utf-8"
    )
    monkeypatch.setenv("REG2MD_PLUGIN_ROOT", "${CLAUDE_PLUGIN_ROOT}")
    monkeypatch.setenv("REG2MD_PLUGIN_DATA", "${PLUGIN_DATA}")
    monkeypatch.setattr(mcp_launcher.Path, "home", lambda: tmp_path)

    assert (
        mcp_launcher._plugin_root() == Path(mcp_launcher.__file__).resolve().parents[1]
    )
    assert mcp_launcher._plugin_data() == tmp_path / ".regulation-to-markdown"
    assert mcp_launcher._plugin_root(str(plugin_root)) == plugin_root.resolve()


def test_plugin_paths_use_expanded_host_directories(tmp_path, monkeypatch):
    plugin_root = tmp_path / "plugin"
    plugin_data = tmp_path / "data"
    plugin_root.mkdir()
    (plugin_root / "pyproject.toml").write_text(
        "[project]\nname='x'\n", encoding="utf-8"
    )
    monkeypatch.setenv("REG2MD_PLUGIN_ROOT", str(plugin_root))
    monkeypatch.setenv("REG2MD_PLUGIN_DATA", str(plugin_data))

    assert mcp_launcher._plugin_root() == plugin_root.resolve()
    assert mcp_launcher._plugin_data() == plugin_data.resolve()
    assert plugin_data.is_dir()


def test_runtime_environ_drops_unresolved_placeholders(monkeypatch):
    monkeypatch.setenv("MINERU_API_TOKEN", "${user_config.mineru_api_token}")
    monkeypatch.setenv("REG2MD_PLUGIN_DATA", "${CLAUDE_PLUGIN_DATA}")
    monkeypatch.setenv("REG2MD_PLUGIN_ROOT", "/resolved/plugin")

    env = mcp_launcher._runtime_environ()

    assert "MINERU_API_TOKEN" not in env
    assert "REG2MD_PLUGIN_DATA" not in env
    assert env["REG2MD_PLUGIN_ROOT"] == "/resolved/plugin"
