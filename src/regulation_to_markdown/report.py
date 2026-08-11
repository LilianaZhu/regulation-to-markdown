from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .findings import load_findings
from .models import Finding, ValidationResult


def _finding_payload(finding: Finding) -> dict[str, Any]:
    return {
        "finding_id": finding.finding_id,
        "category": finding.category,
        "severity": finding.severity.value,
        "status": finding.status.value,
        "pdf_page": finding.pdf_page,
        "md_line_start": finding.md_line_start,
        "md_line_end": finding.md_line_end,
        "official_quote": finding.official_quote,
        "markdown_quote": finding.markdown_quote,
        "proposed_replacement": finding.proposed_replacement,
        "confidence": finding.confidence,
        "source_verified": finding.source_verified,
        "rationale": finding.rationale,
    }


def render_validation_report(
    result: ValidationResult,
    findings: list[Finding],
) -> str:
    frontmatter = {
        "schema_version": 1,
        "report_type": "regulation-to-markdown-validation",
        "status": result.status,
        "generated_at": result.generated_at.isoformat(),
        "document_path": result.document_path,
        "source_pdf_path": result.source_pdf_path,
        "source_sha256": result.source_sha256,
        "summary": {
            "page_count": result.page_count,
            "covered_pages": result.covered_pages,
            "table_count": result.table_count,
            "findings_total": result.findings_total,
            "unresolved_high_findings": result.unresolved_high_findings,
        },
        "checks": [check.model_dump(mode="json") for check in result.checks],
        "findings": [_finding_payload(finding) for finding in findings],
    }
    yaml_text = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    ).strip()

    status_label = {
        "passed": "PASSED",
        "needs_review": "NEEDS REVIEW",
        "failed": "FAILED",
    }[result.status]
    lines = [
        "---",
        yaml_text,
        "---",
        "",
        "# Regulation to Markdown Validation Report",
        "",
        f"**Status:** {status_label}",
        "",
        "## Source",
        "",
        f"- Official PDF: `{result.source_pdf_path}`",
        f"- Final Markdown: `{result.document_path}`",
        f"- PDF SHA-256: `{result.source_sha256}`",
        f"- PDF pages: {result.page_count}",
        "",
        "## Summary",
        "",
        f"- Covered pages: {result.covered_pages}/{result.page_count}",
        f"- HTML tables: {result.table_count}",
        f"- Findings: {result.findings_total}",
        f"- Unresolved high-severity findings: {result.unresolved_high_findings}",
        "",
        "## Release Gates",
        "",
    ]
    for check in result.checks:
        marker = {"pass": "PASS", "warning": "WARN", "fail": "FAIL"}[check.status]
        blocking = " · blocking" if check.blocking else ""
        lines.extend(
            [
                f"### {marker} — {check.title}{blocking}",
                "",
                check.detail,
                "",
            ]
        )

    lines.extend(["## Findings", ""])
    if not findings:
        lines.extend(["No findings were supplied.", ""])
    for finding in findings:
        lines.extend(
            [
                f"### {finding.finding_id} — {finding.category}",
                "",
                f"- Severity: `{finding.severity.value}`",
                f"- Status: `{finding.status.value}`",
                f"- Official PDF page: {finding.pdf_page}",
                f"- Markdown lines: {finding.md_line_start or 'unknown'}"
                + (
                    f"–{finding.md_line_end}"
                    if finding.md_line_end
                    and finding.md_line_end != finding.md_line_start
                    else ""
                ),
                f"- Confidence: {finding.confidence:.2f}",
                f"- Source verified: {'yes' if finding.source_verified else 'no'}",
                "",
                "**Official PDF**",
                "",
                f"> {finding.official_quote.replace(chr(10), chr(10) + '> ')}",
                "",
                "**Current Markdown**",
                "",
                f"> {finding.markdown_quote.replace(chr(10), chr(10) + '> ')}",
                "",
                f"**Rationale:** {finding.rationale}",
                "",
            ]
        )
        if finding.proposed_replacement is not None:
            lines.extend(
                [
                    "**Proposed replacement**",
                    "",
                    f"> {finding.proposed_replacement.replace(chr(10), chr(10) + '> ')}",
                    "",
                ]
            )

    lines.extend(["## Notes", ""])
    lines.extend(f"- {note}" for note in result.notes)
    lines.append("")
    return "\n".join(lines)


def write_validation_report(
    result: ValidationResult,
    report_path: str | Path,
    findings_path: str | Path | None = None,
) -> str:
    findings = load_findings(findings_path) if findings_path else []
    destination = Path(report_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        render_validation_report(result, findings),
        encoding="utf-8",
        newline="\n",
    )
    return str(destination)
