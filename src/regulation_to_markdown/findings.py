from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from .models import Finding, FindingStatus


class FindingError(RuntimeError):
    pass


def load_findings(path: str | Path) -> list[Finding]:
    source = Path(path).resolve()
    if not source.is_file():
        return []
    findings: list[Finding] = []
    for line_number, line in enumerate(
        source.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            findings.append(Finding.model_validate_json(line))
        except Exception as exc:
            raise FindingError(
                f"Invalid finding at {source}:{line_number}: {exc}"
            ) from exc
    return findings


def save_findings(path: str | Path, findings: list[Finding]) -> None:
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        for finding in findings:
            handle.write(finding.model_dump_json() + "\n")


def new_finding_id() -> str:
    return f"finding-{uuid4().hex[:12]}"


def apply_approved_repairs(
    markdown_path: str | Path,
    findings_path: str | Path,
    output_path: str | Path,
    *,
    minimum_confidence: float = 0.95,
) -> dict[str, object]:
    source = Path(markdown_path).resolve()
    destination = Path(output_path).resolve()
    findings_file = Path(findings_path).resolve()
    text = source.read_text(encoding="utf-8")
    findings = load_findings(findings_file)
    applied: list[str] = []

    for finding in findings:
        if finding.status != FindingStatus.APPROVED:
            continue
        if not finding.source_verified:
            raise FindingError(
                f"{finding.finding_id} is approved but source_verified is false"
            )
        if finding.confidence < minimum_confidence:
            raise FindingError(
                f"{finding.finding_id} confidence {finding.confidence} "
                f"is below {minimum_confidence}"
            )
        replacement = finding.proposed_replacement
        if replacement is None:
            raise FindingError(f"{finding.finding_id} has no proposed replacement")
        occurrences = text.count(finding.markdown_quote)
        if occurrences != 1:
            raise FindingError(
                f"{finding.finding_id} markdown_quote occurs {occurrences} times; "
                "expected exactly one"
            )
        text = text.replace(finding.markdown_quote, replacement, 1)
        finding.status = FindingStatus.APPLIED
        applied.append(finding.finding_id)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8", newline="\n")
    save_findings(findings_file, findings)

    audit_path = destination.with_suffix(destination.suffix + ".repairs.jsonl")
    with audit_path.open("w", encoding="utf-8", newline="\n") as handle:
        for finding in findings:
            if finding.finding_id in applied:
                handle.write(
                    json.dumps(
                        {
                            "finding_id": finding.finding_id,
                            "pdf_page": finding.pdf_page,
                            "official_quote": finding.official_quote,
                            "before": finding.markdown_quote,
                            "after": finding.proposed_replacement,
                            "confidence": finding.confidence,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    return {
        "output_path": str(destination),
        "audit_path": str(audit_path),
        "applied_count": len(applied),
        "applied_findings": applied,
    }
