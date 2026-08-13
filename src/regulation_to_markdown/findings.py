from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .audit import audit_completion, load_audit_manifest
from .models import Finding, FindingStatus
from .pdf import sha256_file


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


def _load_repair_log(path: Path) -> list[dict[str, Any]]:
    repairs: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            repair = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FindingError(
                f"Invalid repair record at {path}:{line_number}: {exc}"
            ) from exc
        required = {"finding_id", "pdf_page", "official_quote", "before", "after"}
        missing = sorted(required - repair.keys())
        if missing:
            raise FindingError(
                f"Repair record at {path}:{line_number} is missing {missing}"
            )
        repairs.append(repair)
    return repairs


def synchronize_findings_with_verified_output(
    final_markdown_path: str | Path,
    findings_path: str | Path,
    audit_manifest_path: str | Path,
    repairs_path: str | Path | None = None,
) -> dict[str, object]:
    """Mark repaired findings verified only after deterministic final-file proof."""
    final_markdown = Path(final_markdown_path).resolve()
    findings_file = Path(findings_path).resolve()
    manifest = load_audit_manifest(audit_manifest_path)
    repair_log = (
        Path(repairs_path).resolve()
        if repairs_path
        else final_markdown.with_suffix(final_markdown.suffix + ".repairs.jsonl")
    )

    if not final_markdown.is_file():
        raise FindingError(f"Final Markdown not found: {final_markdown}")
    if not repair_log.is_file():
        return {
            "verified_count": 0,
            "verified_findings": [],
            "repair_log": None,
        }

    completion = audit_completion(manifest)
    if not completion["complete"]:
        raise FindingError(
            "Cannot synchronize findings before audit and independent "
            f"verification are complete: {completion}"
        )
    final_hash = sha256_file(final_markdown)
    if manifest.final_markdown_sha256 != final_hash:
        raise FindingError(
            "Cannot synchronize findings because the final Markdown hash "
            "does not match the independently verified file"
        )

    original_markdown = Path(manifest.markdown_path).resolve()
    if not original_markdown.is_file():
        raise FindingError(
            f"Audited pre-repair Markdown not found: {original_markdown}"
        )
    if sha256_file(original_markdown) != manifest.markdown_sha256:
        raise FindingError(
            "Cannot synchronize findings because the audited pre-repair "
            "Markdown hash has changed"
        )

    repairs = _load_repair_log(repair_log)
    replayed = original_markdown.read_text(encoding="utf-8")
    repair_ids: set[str] = set()
    for repair in repairs:
        finding_id = str(repair["finding_id"])
        if finding_id in repair_ids:
            raise FindingError(f"Duplicate repair record for {finding_id}")
        repair_ids.add(finding_id)
        before = str(repair["before"])
        after = str(repair["after"])
        occurrences = replayed.count(before)
        if occurrences != 1:
            raise FindingError(
                f"Cannot replay {finding_id}: repair anchor occurs "
                f"{occurrences} times; expected exactly one"
            )
        replayed = replayed.replace(before, after, 1)

    final_text = final_markdown.read_text(encoding="utf-8")
    if replayed != final_text:
        raise FindingError(
            "Final Markdown is not the exact result recorded by the repair log"
        )

    findings = load_findings(findings_file)
    findings_by_id = {finding.finding_id: finding for finding in findings}
    if len(findings_by_id) != len(findings):
        raise FindingError("Duplicate finding IDs prevent final-output synchronization")

    verified: list[str] = []
    for repair in repairs:
        finding_id = str(repair["finding_id"])
        finding = findings_by_id.get(finding_id)
        if finding is None:
            raise FindingError(f"Repair log references unknown finding {finding_id}")
        if finding.status == FindingStatus.REJECTED:
            raise FindingError(f"Rejected finding {finding_id} has a repair record")
        if int(repair["pdf_page"]) != finding.pdf_page:
            raise FindingError(f"PDF page mismatch for repaired finding {finding_id}")
        confidence = float(repair.get("confidence", finding.confidence))
        if confidence < 0.95:
            raise FindingError(
                f"Repair evidence confidence for {finding_id} is below 0.95"
            )

        finding.stage = "verify"
        finding.status = FindingStatus.VERIFIED
        finding.source_verified = True
        finding.official_quote = str(repair["official_quote"])
        finding.markdown_quote = str(repair["after"])
        finding.proposed_replacement = str(repair["after"])
        finding.confidence = confidence
        sync_note = (
            "已根据修复日志、最终文件哈希和已完成的独立复核自动同步为 verified。"
        )
        if not finding.reviewer_notes:
            finding.reviewer_notes = sync_note
        elif sync_note not in finding.reviewer_notes:
            finding.reviewer_notes = f"{finding.reviewer_notes} {sync_note}"
        verified.append(finding_id)

    save_findings(findings_file, findings)
    return {
        "verified_count": len(verified),
        "verified_findings": verified,
        "repair_log": str(repair_log),
    }
