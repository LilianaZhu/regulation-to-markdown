from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from .models import (
    AuditManifest,
    AuditWindow,
    ReviewWindowStatus,
    utc_now,
)
from .pdf import inspect_pdf, sha256_file


class AuditError(RuntimeError):
    pass


def _save(path: Path, manifest: AuditManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    os.replace(temporary, path)


def load_audit_manifest(path: str | Path) -> AuditManifest:
    source = Path(path).resolve()
    if not source.is_file():
        raise AuditError(f"Audit manifest not found: {source}")
    return AuditManifest.model_validate_json(source.read_text(encoding="utf-8"))


def initialize_audit_manifest(
    source_pdf_path: str | Path,
    markdown_path: str | Path,
    manifest_path: str | Path,
    *,
    window_size: int = 20,
) -> AuditManifest:
    if window_size < 1 or window_size > 50:
        raise AuditError("window_size must be between 1 and 50")
    pdf = inspect_pdf(source_pdf_path)
    markdown = Path(markdown_path).resolve()
    if not markdown.is_file():
        raise AuditError(f"Markdown not found: {markdown}")

    windows = [
        AuditWindow(
            start_page=start,
            end_page=min(pdf.page_count, start + window_size - 1),
        )
        for start in range(1, pdf.page_count + 1, window_size)
    ]
    manifest = AuditManifest(
        source_pdf_path=pdf.path,
        source_sha256=pdf.sha256,
        markdown_path=str(markdown),
        markdown_sha256=sha256_file(markdown),
        page_count=pdf.page_count,
        window_size=window_size,
        windows=windows,
    )
    _save(Path(manifest_path).resolve(), manifest)
    return manifest


def record_audit_window(
    manifest_path: str | Path,
    start_page: int,
    end_page: int,
    stage: Literal["audit", "verify"],
    status: ReviewWindowStatus,
    notes: str | None = None,
    markdown_path: str | Path | None = None,
) -> AuditManifest:
    path = Path(manifest_path).resolve()
    manifest = load_audit_manifest(path)
    matching = [
        window
        for window in manifest.windows
        if window.start_page == start_page and window.end_page == end_page
    ]
    if len(matching) != 1:
        raise AuditError(
            f"Audit window {start_page}-{end_page} is not defined in the manifest"
        )
    window = matching[0]
    if stage == "audit":
        window.audit_status = status
        window.audit_notes = notes
    else:
        if window.audit_status != ReviewWindowStatus.COMPLETED:
            raise AuditError("Independent verification requires completed audit")
        if markdown_path is None:
            raise AuditError("Verification requires the final Markdown path")
        final_hash = sha256_file(markdown_path)
        if (
            manifest.final_markdown_sha256 is not None
            and manifest.final_markdown_sha256 != final_hash
        ):
            raise AuditError(
                "Verification windows reference different Markdown versions"
            )
        manifest.final_markdown_sha256 = final_hash
        window.verify_status = status
        window.verify_notes = notes
    manifest.updated_at = utc_now()
    _save(path, manifest)
    return manifest


def audit_completion(manifest: AuditManifest) -> dict[str, object]:
    audit_incomplete = [
        f"{window.start_page}-{window.end_page}"
        for window in manifest.windows
        if window.audit_status != ReviewWindowStatus.COMPLETED
    ]
    verify_incomplete = [
        f"{window.start_page}-{window.end_page}"
        for window in manifest.windows
        if window.verify_status != ReviewWindowStatus.COMPLETED
    ]
    return {
        "complete": not audit_incomplete and not verify_incomplete,
        "audit_incomplete": audit_incomplete,
        "verify_incomplete": verify_incomplete,
    }
