from __future__ import annotations

import asyncio
import json
from pathlib import Path

from regulation_to_markdown.mcp_server import mcp

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cursor_plugin_manifest_and_skill():
    manifest = json.loads(
        (PROJECT_ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    skill = (PROJECT_ROOT / "skills" / "regulation-to-markdown" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert manifest["name"] == "regulation-to-markdown"
    assert manifest["repository"].endswith("/Lilianablog/regulation-to-markdown")
    assert manifest["logo"] == "assets/logo.svg"
    assert "MINERU_API_TOKEN" in manifest["variables"]["properties"]
    assert skill.startswith("---\nname: regulation-to-markdown\n")
    assert "official PDF is the only authority" in skill
    assert skill.index("### 4. Merge normalized batches") < skill.index(
        "### 5. Audit in bounded windows"
    )


def test_local_installer_uses_file_allowlist():
    installer = (PROJECT_ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "$DirectoryExtensions" in installer
    assert "Get-ChildItem -Recurse -File $SourceRoot" in installer
    assert "Copy-Item -Recurse" not in installer


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
