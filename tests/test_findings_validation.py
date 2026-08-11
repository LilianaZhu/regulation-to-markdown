from __future__ import annotations

import pytest
import yaml
from pypdf import PdfReader

from regulation_to_markdown.audit import (
    initialize_audit_manifest,
    record_audit_window,
)
from regulation_to_markdown.findings import (
    FindingError,
    apply_approved_repairs,
    load_findings,
    save_findings,
)
from regulation_to_markdown.models import (
    Finding,
    FindingSeverity,
    FindingStatus,
    ReviewWindowStatus,
)
from regulation_to_markdown.report import write_validation_report
from regulation_to_markdown.validate import validate_document


def _complete_audit(pdf, markdown, manifest_path):
    page_count = len(PdfReader(str(pdf)).pages)
    initialize_audit_manifest(pdf, markdown, manifest_path)
    record_audit_window(
        manifest_path,
        1,
        page_count,
        "audit",
        ReviewWindowStatus.COMPLETED,
    )
    record_audit_window(
        manifest_path,
        1,
        page_count,
        "verify",
        ReviewWindowStatus.COMPLETED,
        markdown_path=markdown,
    )


def test_apply_only_approved_source_verified_repair(tmp_path):
    markdown = tmp_path / "document.md"
    findings_path = tmp_path / "findings.jsonl"
    output = tmp_path / "repaired.md"
    markdown.write_text("Before broken text after.\n", encoding="utf-8")
    finding = Finding(
        finding_id="finding-1",
        category="ocr_join",
        severity=FindingSeverity.HIGH,
        status=FindingStatus.APPROVED,
        pdf_page=7,
        official_quote="correct text",
        markdown_quote="broken text",
        proposed_replacement="correct text",
        rationale="Verified against the official PDF.",
        confidence=0.99,
        source_verified=True,
    )
    save_findings(findings_path, [finding])

    result = apply_approved_repairs(markdown, findings_path, output)

    assert result["applied_count"] == 1
    assert "correct text" in output.read_text(encoding="utf-8")
    assert load_findings(findings_path)[0].status == FindingStatus.APPLIED


def test_validation_report_is_human_and_machine_readable(tmp_path, make_pdf):
    pdf = make_pdf(tmp_path / "source.pdf", 2)
    markdown = tmp_path / "final.md"
    report = tmp_path / "validation-report.md"
    audit_manifest = tmp_path / "audit-manifest.json"
    markdown.write_text(
        "<!-- pdf-page: 1 -->\n\nPage one.\n\n<!-- pdf-page: 2 -->\n\nPage two.\n",
        encoding="utf-8",
    )

    _complete_audit(pdf, markdown, audit_manifest)
    result = validate_document(
        markdown,
        pdf,
        audit_manifest_path=audit_manifest,
    )
    write_validation_report(result, report)
    rendered = report.read_text(encoding="utf-8")
    frontmatter = rendered.split("---", 2)[1]
    parsed = yaml.safe_load(frontmatter)

    assert result.status == "passed"
    assert parsed["schema_version"] == 1
    assert parsed["status"] == "passed"
    assert "# Regulation to Markdown Validation Report" in rendered


def test_repair_blocks_unverified_source(tmp_path):
    markdown = tmp_path / "document.md"
    findings_path = tmp_path / "findings.jsonl"
    markdown.write_text("broken\n", encoding="utf-8")
    finding = Finding(
        finding_id="finding-unverified",
        category="missing_text",
        severity=FindingSeverity.HIGH,
        status=FindingStatus.APPROVED,
        pdf_page=1,
        official_quote="correct",
        markdown_quote="broken",
        proposed_replacement="correct",
        rationale="Not yet checked.",
        confidence=0.99,
        source_verified=False,
    )
    save_findings(findings_path, [finding])

    with pytest.raises(FindingError, match="source_verified is false"):
        apply_approved_repairs(
            markdown,
            findings_path,
            tmp_path / "output.md",
        )


def test_validation_blocks_open_high_finding(tmp_path, make_pdf):
    pdf = make_pdf(tmp_path / "source.pdf", 1)
    markdown = tmp_path / "final.md"
    findings_path = tmp_path / "findings.jsonl"
    audit_manifest = tmp_path / "audit-manifest.json"
    markdown.write_text("<!-- pdf-page: 1 -->\n\nText.\n", encoding="utf-8")
    finding = Finding(
        finding_id="finding-open",
        category="missing_text",
        severity=FindingSeverity.HIGH,
        pdf_page=1,
        official_quote="Official.",
        markdown_quote="Text.",
        rationale="Requires source restoration.",
        confidence=0.99,
    )
    save_findings(findings_path, [finding])
    _complete_audit(pdf, markdown, audit_manifest)

    result = validate_document(
        markdown,
        pdf,
        findings_path,
        audit_manifest,
    )

    assert result.status == "failed"
    assert result.unresolved_high_findings == 1


def test_validation_blocks_missing_ai_audit(tmp_path, make_pdf):
    pdf = make_pdf(tmp_path / "source.pdf", 1)
    markdown = tmp_path / "final.md"
    markdown.write_text("<!-- pdf-page: 1 -->\n\nText.\n", encoding="utf-8")

    result = validate_document(markdown, pdf)

    assert result.status == "failed"
    assert any(
        check.check_id == "ai-audit-completion" and check.status == "fail"
        for check in result.checks
    )
