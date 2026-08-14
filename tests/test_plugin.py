from __future__ import annotations

import asyncio
import json
from pathlib import Path

from regulation_to_markdown.mcp_server import mcp

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_agent_and_claude_plugin_manifests_and_skill():
    agent_manifest = json.loads(
        (PROJECT_ROOT / "plugin.json").read_text(encoding="utf-8")
    )
    claude_manifest = json.loads(
        (PROJECT_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    marketplace = json.loads(
        (PROJECT_ROOT / ".claude-plugin" / "marketplace.json").read_text(
            encoding="utf-8"
        )
    )
    agent_mcp = json.loads((PROJECT_ROOT / "mcp.json").read_text(encoding="utf-8"))
    claude_mcp = json.loads((PROJECT_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    skill = (PROJECT_ROOT / "skills" / "regulation-to-markdown" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert agent_manifest["$schema"].endswith("/1.0.0/plugin.schema.json")
    assert agent_manifest["name"] == "regulation-to-markdown"
    assert claude_manifest["name"] == "regulation-to-markdown"
    assert claude_manifest["version"] == agent_manifest["version"] == "0.2.2"
    token_config = claude_manifest["userConfig"]["mineru_api_token"]
    assert token_config["sensitive"] is True
    assert token_config["required"] is True
    assert "https://mineru.net/apiManage/token" in token_config["description"]
    assert marketplace["plugins"][0]["source"] == "./"
    assert marketplace["plugins"][0]["version"] == claude_manifest["version"]
    assert agent_mcp["$schema"].endswith("/1.0.0/mcp.schema.json")
    assert "${PLUGIN_ROOT}" in json.dumps(agent_mcp)
    assert "${CLAUDE_PLUGIN_ROOT}" in json.dumps(claude_mcp)
    assert "${user_config.mineru_api_token}" in json.dumps(claude_mcp)
    assert (PROJECT_ROOT / "scripts" / "mcp_launcher.py").is_file()
    assert not (PROJECT_ROOT / ".cursor-plugin" / "plugin.json").exists()
    assert not (PROJECT_ROOT / "commands" / "regulation-to-markdown.md").exists()
    assert skill.startswith("---\nname: regulation-to-markdown\n")
    assert "official PDF is the only authority" in skill
    assert skill.index("### 4. Merge normalized batches") < skill.index(
        "### 5. Audit in bounded windows"
    )


def test_installer_targets_claude_plugin_workflow():
    installer = (PROJECT_ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "InstallClaudePlugin" in installer
    assert "claude plugin marketplace add" in installer
    assert "claude plugin install" in installer
    assert "else {\n    python (Join-Path $ProjectRoot" in installer
    assert ".cursor\\plugins\\local" not in installer


def test_ci_validates_current_plugin_manifests():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert ".cursor-plugin/plugin.json" not in workflow
    for manifest in (
        "plugin.json",
        "mcp.json",
        ".mcp.json",
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
    ):
        assert f'"{manifest}"' in workflow


def test_mcp_exposes_expected_tools():
    tools = asyncio.run(mcp.list_tools())
    names = {tool.name for tool in tools}

    assert {
        "inspect_pdf_and_propose_splits",
        "confirm_split_plan",
        "submit_confirmed_batches_to_mineru",
        "mineru_batch_status",
        "wait_for_and_download_mineru",
        "locate_mineru_output",
        "render_official_pdf_pages",
        "update_job_stage",
        "initialize_ai_audit",
        "record_ai_review_window",
        "normalize_mineru_batch",
        "merge_normalized_batches",
        "apply_source_verified_repairs",
        "validate_and_write_report",
        "export_final_artifacts",
    } <= names


def test_mcp_preflight_tool_returns_structured_plans(tmp_path, make_pdf):
    pdf = make_pdf(tmp_path / "source.pdf", 3)

    result = asyncio.run(
        mcp.call_tool(
            "inspect_pdf_and_propose_splits",
            {
                "pdf_path": str(pdf),
                "work_dir": str(tmp_path / "work"),
                "reliable_pages": 2,
                "overlap_pages": 1,
            },
        )
    )

    assert result.is_error is not True
    assert result.structured_content["source"]["page_count"] == 3
    assert result.structured_content["confirmation_required"] is True
    assert len(result.structured_content["plans"]) == 2
    assert (tmp_path / "work" / "job.json").is_file()
    assert '"event": "pdf_inspected"' in (tmp_path / "work" / "events.jsonl").read_text(
        encoding="utf-8"
    )

    confirmed = asyncio.run(
        mcp.call_tool(
            "confirm_split_plan",
            {
                "work_dir": str(tmp_path / "work"),
                "plan": result.structured_content["plans"][0],
            },
        )
    )

    assert confirmed.is_error is not True
    assert confirmed.structured_content["state"] == "split_confirmed"
    assert len(confirmed.structured_content["batches"]) == 2
    assert all(
        Path(batch["file_path"]).is_file()
        for batch in confirmed.structured_content["batches"]
    )
