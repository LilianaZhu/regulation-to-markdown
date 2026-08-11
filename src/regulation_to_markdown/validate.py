from __future__ import annotations

import re
from pathlib import Path

from .audit import AuditError, audit_completion, load_audit_manifest
from .findings import load_findings
from .merge import MergeError, covered_pages, page_segments
from .models import (
    FindingSeverity,
    FindingStatus,
    ValidationCheck,
    ValidationResult,
)
from .pdf import inspect_pdf, sha256_file


def _image_targets(markdown: str) -> list[str]:
    return [
        match.group(2).strip()
        for match in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", markdown)
    ]


def _table_shapes(markdown: str) -> list[list[int]]:
    shapes: list[list[int]] = []
    for table in re.findall(r"<table>.*?</table>", markdown, flags=re.DOTALL):
        rows = re.findall(r"<tr>.*?</tr>", table, flags=re.DOTALL)
        shapes.append([len(re.findall(r"<t[dh]>", row)) for row in rows])
    return shapes


def validate_document(
    markdown_path: str | Path,
    source_pdf_path: str | Path,
    findings_path: str | Path | None = None,
    audit_manifest_path: str | Path | None = None,
) -> ValidationResult:
    markdown_file = Path(markdown_path).resolve()
    source_pdf = Path(source_pdf_path).resolve()
    markdown = markdown_file.read_text(encoding="utf-8")
    pdf_info = inspect_pdf(source_pdf)
    checks: list[ValidationCheck] = []

    try:
        segments = page_segments(markdown)
        covered = covered_pages(markdown)
        duplicate_error = None
    except MergeError as exc:
        segments = {}
        covered = covered_pages(markdown)
        duplicate_error = str(exc)

    expected = set(range(1, pdf_info.page_count + 1))
    missing = sorted(expected - covered)
    extra = sorted(covered - expected)
    checks.append(
        ValidationCheck(
            check_id="page-coverage",
            title="PDF page coverage",
            status="pass" if covered == expected else "fail",
            detail=(
                f"Covered all {pdf_info.page_count} pages"
                if covered == expected
                else f"Missing pages={missing}; extra pages={extra}"
            ),
            blocking=True,
        )
    )
    checks.append(
        ValidationCheck(
            check_id="duplicate-pages",
            title="Duplicate page markers",
            status="pass" if duplicate_error is None else "fail",
            detail=duplicate_error or f"{len(segments)} page markers are unique",
            blocking=True,
        )
    )

    broken_images: list[str] = []
    for target in _image_targets(markdown):
        if re.match(r"^(?:https?|data):", target, flags=re.IGNORECASE):
            continue
        if not (markdown_file.parent / target).is_file():
            broken_images.append(target)
    checks.append(
        ValidationCheck(
            check_id="image-assets",
            title="Image assets",
            status="pass" if not broken_images else "fail",
            detail=(
                "No broken local image references"
                if not broken_images
                else f"Missing image assets: {broken_images}"
            ),
            blocking=True,
        )
    )

    shapes = _table_shapes(markdown)
    malformed_tables = [
        index + 1
        for index, row_sizes in enumerate(shapes)
        if row_sizes and len(set(row_sizes)) > 1
    ]
    checks.append(
        ValidationCheck(
            check_id="table-shapes",
            title="HTML table row shapes",
            status="pass" if not malformed_tables else "warning",
            detail=(
                f"Checked {len(shapes)} tables"
                if not malformed_tables
                else f"Inconsistent row widths in tables {malformed_tables}"
            ),
            blocking=False,
        )
    )

    code_fences = len(re.findall(r"(?m)^```", markdown))
    checks.append(
        ValidationCheck(
            check_id="code-fences",
            title="Code fences",
            status="pass" if code_fences % 2 == 0 else "fail",
            detail=f"Found {code_fences} code-fence lines",
            blocking=True,
        )
    )

    audit_detail = "Audit manifest was not supplied"
    audit_passed = False
    if audit_manifest_path:
        try:
            audit_manifest = load_audit_manifest(audit_manifest_path)
            completion = audit_completion(audit_manifest)
            source_matches = audit_manifest.source_sha256 == pdf_info.sha256
            final_matches = audit_manifest.final_markdown_sha256 == sha256_file(
                markdown_file
            )
            audit_passed = bool(
                completion["complete"] and source_matches and final_matches
            )
            audit_detail = (
                "All audit and independent-verification windows are complete"
                if audit_passed
                else "Audit incomplete or file hashes differ: "
                f"{completion}; source_matches={source_matches}; "
                f"final_matches={final_matches}"
            )
        except AuditError as exc:
            audit_detail = str(exc)
    checks.append(
        ValidationCheck(
            check_id="ai-audit-completion",
            title="AI audit and independent verification",
            status="pass" if audit_passed else "fail",
            detail=audit_detail,
            blocking=True,
        )
    )

    findings = load_findings(findings_path) if findings_path else []
    unresolved = [
        finding
        for finding in findings
        if finding.severity in {FindingSeverity.HIGH, FindingSeverity.CRITICAL}
        and finding.status not in {FindingStatus.VERIFIED, FindingStatus.REJECTED}
    ]
    unverified_applied = [
        finding
        for finding in findings
        if finding.status in {FindingStatus.APPLIED, FindingStatus.VERIFIED}
        and not finding.source_verified
    ]
    checks.append(
        ValidationCheck(
            check_id="high-findings",
            title="Unresolved high-severity findings",
            status="pass" if not unresolved else "fail",
            detail=(
                "No unresolved high-severity findings"
                if not unresolved
                else ", ".join(item.finding_id for item in unresolved)
            ),
            blocking=True,
        )
    )
    checks.append(
        ValidationCheck(
            check_id="repair-evidence",
            title="Source evidence for applied repairs",
            status="pass" if not unverified_applied else "fail",
            detail=(
                "All applied repairs are source-verified"
                if not unverified_applied
                else ", ".join(item.finding_id for item in unverified_applied)
            ),
            blocking=True,
        )
    )

    failed = any(check.status == "fail" and check.blocking for check in checks)
    warnings = any(check.status == "warning" for check in checks)
    status = "failed" if failed else "needs_review" if warnings else "passed"
    return ValidationResult(
        document_path=str(markdown_file),
        source_pdf_path=str(source_pdf),
        source_sha256=pdf_info.sha256,
        status=status,
        page_count=pdf_info.page_count,
        covered_pages=len(covered & expected),
        table_count=len(shapes),
        findings_total=len(findings),
        unresolved_high_findings=len(unresolved),
        checks=checks,
        notes=[
            "Structural validation does not replace independent AI/PDF visual review.",
            "Official-source anomalies should remain verbatim and be documented.",
        ],
    )
