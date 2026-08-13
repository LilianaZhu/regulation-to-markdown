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
    synchronize_findings_with_verified_output,
)
from regulation_to_markdown.models import (
    Finding,
    FindingSeverity,
    FindingStatus,
    ReviewWindowStatus,
    VisualClassification,
    VisualDisposition,
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


def test_synchronize_repaired_finding_with_verified_final_output(tmp_path, make_pdf):
    pdf = make_pdf(tmp_path / "source.pdf", 1)
    merged = tmp_path / "merged.md"
    final = tmp_path / "final.md"
    findings_path = tmp_path / "findings.jsonl"
    audit_manifest = tmp_path / "audit-manifest.json"
    merged.write_text("<!-- pdf-page: 1 -->\n\nBroken text.\n", encoding="utf-8")
    finding = Finding(
        finding_id="finding-repaired",
        category="wrong_text",
        severity=FindingSeverity.HIGH,
        status=FindingStatus.APPROVED,
        pdf_page=1,
        official_quote="Correct text.",
        markdown_quote="Broken text.",
        proposed_replacement="Correct text.",
        rationale="已对照官方原文。",
        confidence=1,
        source_verified=True,
    )
    save_findings(findings_path, [finding])
    initialize_audit_manifest(pdf, merged, audit_manifest)
    record_audit_window(
        audit_manifest,
        1,
        1,
        "audit",
        ReviewWindowStatus.COMPLETED,
    )
    apply_approved_repairs(merged, findings_path, final)
    stale_finding = load_findings(findings_path)[0]
    stale_finding.status = FindingStatus.OPEN
    stale_finding.source_verified = False
    stale_finding.official_quote = "Truncated audit-stage quote."
    save_findings(findings_path, [stale_finding])
    record_audit_window(
        audit_manifest,
        1,
        1,
        "verify",
        ReviewWindowStatus.COMPLETED,
        markdown_path=final,
    )

    sync = synchronize_findings_with_verified_output(
        final,
        findings_path,
        audit_manifest,
    )
    synchronize_findings_with_verified_output(
        final,
        findings_path,
        audit_manifest,
    )
    synchronized = load_findings(findings_path)[0]
    result = validate_document(final, pdf, findings_path, audit_manifest)

    assert sync["verified_findings"] == ["finding-repaired"]
    assert synchronized.status == FindingStatus.VERIFIED
    assert synchronized.stage == "verify"
    assert synchronized.source_verified is True
    assert synchronized.official_quote == "Correct text."
    assert synchronized.markdown_quote == "Correct text."
    assert synchronized.reviewer_notes.count("自动同步为 verified") == 1
    assert result.status == "passed"


def test_synchronization_rejects_final_output_not_reproduced_by_repair_log(
    tmp_path,
    make_pdf,
):
    pdf = make_pdf(tmp_path / "source.pdf", 1)
    merged = tmp_path / "merged.md"
    final = tmp_path / "final.md"
    findings_path = tmp_path / "findings.jsonl"
    audit_manifest = tmp_path / "audit-manifest.json"
    merged.write_text("<!-- pdf-page: 1 -->\n\nBroken text.\n", encoding="utf-8")
    save_findings(
        findings_path,
        [
            Finding(
                finding_id="finding-repaired",
                category="wrong_text",
                severity=FindingSeverity.HIGH,
                status=FindingStatus.APPROVED,
                pdf_page=1,
                official_quote="Correct text.",
                markdown_quote="Broken text.",
                proposed_replacement="Correct text.",
                rationale="已对照官方原文。",
                confidence=1,
                source_verified=True,
            )
        ],
    )
    initialize_audit_manifest(pdf, merged, audit_manifest)
    record_audit_window(
        audit_manifest,
        1,
        1,
        "audit",
        ReviewWindowStatus.COMPLETED,
    )
    apply_approved_repairs(merged, findings_path, final)
    final.write_text(
        "<!-- pdf-page: 1 -->\n\nDifferent final text.\n",
        encoding="utf-8",
    )
    record_audit_window(
        audit_manifest,
        1,
        1,
        "verify",
        ReviewWindowStatus.COMPLETED,
        markdown_path=final,
    )

    with pytest.raises(FindingError, match="exact result recorded"):
        synchronize_findings_with_verified_output(
            final,
            findings_path,
            audit_manifest,
        )
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
    assert parsed["schema_version"] == 2
    assert parsed["status"] == "passed"
    assert parsed["release_allowed"] is True
    assert parsed["files"]["source_pdf"] == "source.pdf"
    assert "# 法规 Markdown 核验报告" in rendered
    assert "核验结论：可以发布" in rendered
    assert str(tmp_path) not in rendered


def test_report_summarizes_verified_findings_without_repeating_evidence(
    tmp_path,
    make_pdf,
):
    pdf = make_pdf(tmp_path / "source.pdf", 1)
    markdown = tmp_path / "final.md"
    findings_path = tmp_path / "findings.jsonl"
    report = tmp_path / "validation-report.md"
    audit_manifest = tmp_path / "audit-manifest.json"
    markdown.write_text("<!-- pdf-page: 1 -->\n\nCorrect text.\n", encoding="utf-8")
    finding = Finding(
        finding_id="finding-verified",
        category="wrong_text",
        severity=FindingSeverity.HIGH,
        status=FindingStatus.VERIFIED,
        pdf_page=1,
        official_quote="Correct text.",
        markdown_quote="Correct text.",
        proposed_replacement="Correct text.",
        rationale="已对照官方原文复核。",
        confidence=1,
        source_verified=True,
    )
    save_findings(findings_path, [finding])
    _complete_audit(pdf, markdown, audit_manifest)
    result = validate_document(
        markdown,
        pdf,
        findings_path,
        audit_manifest,
    )

    write_validation_report(
        result,
        report,
        findings_path,
        audit_manifest,
    )
    rendered = report.read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(rendered.split("---", 2)[1])

    assert frontmatter["summary"]["findings"]["verified"] == 1
    assert frontmatter["evidence_files"] == [
        "findings.jsonl",
        "audit-manifest.json",
    ]
    assert "高 1 项" in rendered
    assert "PDF 页码：1" in rendered
    assert "finding-verified" not in rendered
    assert "Correct text." not in rendered


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
    report = tmp_path / "validation-report.md"
    write_validation_report(result, report, findings_path, audit_manifest)
    rendered = report.read_text(encoding="utf-8")

    assert result.status == "failed"
    assert result.unresolved_high_findings == 1
    assert "核验结论：不可发布" in rendered
    assert "finding-open" in rendered
    assert "Requires source restoration." in rendered


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


def test_meaningful_visual_description_requires_human_review(tmp_path, make_pdf):
    pdf = make_pdf(tmp_path / "source.pdf", 1)
    markdown = tmp_path / "final.md"
    findings_path = tmp_path / "findings.jsonl"
    audit_manifest = tmp_path / "audit-manifest.json"
    report = tmp_path / "validation-report.md"
    markdown.write_text(
        "<!-- pdf-page: 1 -->\n\n"
        "[Non-normative visual description: A flow chart connects A to B.]\n",
        encoding="utf-8",
    )
    save_findings(
        findings_path,
        [
            Finding(
                finding_id="visual-meaningful",
                category="meaningful_visual",
                severity=FindingSeverity.MEDIUM,
                status=FindingStatus.VERIFIED,
                pdf_page=1,
                official_quote="Flow chart from A to B",
                markdown_quote="A flow chart connects A to B.",
                rationale="The diagram explains the regulated process.",
                confidence=1,
                source_verified=True,
                visual_classification=VisualClassification.MEANINGFUL,
                visual_disposition=VisualDisposition.DESCRIBED,
                visual_description="流程图显示 A 指向 B。",
                human_review_required=True,
                human_reviewed=False,
            )
        ],
    )
    _complete_audit(pdf, markdown, audit_manifest)

    result = validate_document(markdown, pdf, findings_path, audit_manifest)
    write_validation_report(
        result,
        report,
        findings_path,
        audit_manifest,
    )
    rendered = report.read_text(encoding="utf-8")

    assert result.status == "needs_review"
    assert "条文相关图片已转成文字描述，仍需人工复核" in rendered
    assert "PDF 第 1 页｜条文相关图片｜⚠️ 需要人工复核" in rendered

    reviewed = load_findings(findings_path)
    reviewed[0].human_reviewed = True
    save_findings(findings_path, reviewed)
    reviewed_result = validate_document(
        markdown,
        pdf,
        findings_path,
        audit_manifest,
    )
    assert reviewed_result.status == "passed"


def test_omitted_non_substantive_visual_is_reported_without_warning(
    tmp_path,
    make_pdf,
):
    pdf = make_pdf(tmp_path / "source.pdf", 1)
    markdown = tmp_path / "final.md"
    findings_path = tmp_path / "findings.jsonl"
    audit_manifest = tmp_path / "audit-manifest.json"
    report = tmp_path / "validation-report.md"
    markdown.write_text("<!-- pdf-page: 1 -->\n\nRegulatory text.\n", encoding="utf-8")
    save_findings(
        findings_path,
        [
            Finding(
                finding_id="visual-logo",
                category="non_substantive_visual",
                severity=FindingSeverity.LOW,
                status=FindingStatus.VERIFIED,
                pdf_page=1,
                official_quote="OJK logo and signature verification QR code",
                markdown_quote="",
                rationale="The images do not explain or qualify a provision.",
                confidence=1,
                source_verified=True,
                visual_classification=VisualClassification.NON_SUBSTANTIVE,
                visual_disposition=VisualDisposition.OMITTED,
                visual_description="省略 OJK logo 和电子签名核验二维码。",
            )
        ],
    )
    _complete_audit(pdf, markdown, audit_manifest)

    result = validate_document(markdown, pdf, findings_path, audit_manifest)
    write_validation_report(
        result,
        report,
        findings_path,
        audit_manifest,
    )
    rendered = report.read_text(encoding="utf-8")

    assert result.status == "passed"
    assert "PDF 第 1 页｜已省略低信息图片" in rendered
    assert "省略 OJK logo 和电子签名核验二维码" in rendered
    assert "⚠️" not in rendered


def test_unclassified_image_finding_blocks_release(tmp_path, make_pdf):
    pdf = make_pdf(tmp_path / "source.pdf", 1)
    markdown = tmp_path / "final.md"
    findings_path = tmp_path / "findings.jsonl"
    audit_manifest = tmp_path / "audit-manifest.json"
    markdown.write_text("<!-- pdf-page: 1 -->\n\nText.\n", encoding="utf-8")
    save_findings(
        findings_path,
        [
            Finding(
                finding_id="visual-unclassified",
                category="broken_image",
                severity=FindingSeverity.MEDIUM,
                status=FindingStatus.VERIFIED,
                pdf_page=1,
                official_quote="Image",
                markdown_quote="",
                rationale="The image has not been classified.",
                confidence=1,
                source_verified=True,
            )
        ],
    )
    _complete_audit(pdf, markdown, audit_manifest)

    result = validate_document(markdown, pdf, findings_path, audit_manifest)

    assert result.status == "failed"
    assert any(
        check.check_id == "visual-content" and check.status == "fail"
        for check in result.checks
    )
