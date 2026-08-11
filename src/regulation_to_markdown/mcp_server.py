from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from mcp.server import MCPServer

from .audit import initialize_audit_manifest, record_audit_window
from .findings import apply_approved_repairs
from .merge import merge_batches
from .mineru import MinerUClient
from .models import (
    DocumentJob,
    JobState,
    MinerUResult,
    PageBatch,
    ReviewWindowStatus,
    SplitPlan,
)
from .normalize import find_mineru_files, normalize_batch
from .paths import within_work_dir
from .pdf import inspect_pdf, propose_split_plans, render_pdf_pages, split_pdf
from .report import write_validation_report
from .state import JobStore
from .validate import validate_document

mcp = MCPServer("regulation-to-markdown")


def _match_results_to_batches(
    results: list[MinerUResult],
    batches: list[PageBatch],
) -> list[MinerUResult]:
    matched: list[MinerUResult] = []
    used: set[int] = set()
    for batch in batches:
        candidates = [
            index
            for index, result in enumerate(results)
            if index not in used
            and (
                (result.data_id and result.data_id == batch.data_id)
                or (
                    not result.data_id
                    and batch.file_path
                    and result.file_name == Path(batch.file_path).name
                )
            )
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"MinerU result for batch {batch.index} is not unique; "
                f"matches={len(candidates)}"
            )
        used.add(candidates[0])
        matched.append(results[candidates[0]])
    if len(used) != len(results):
        raise ValueError("MinerU returned unmatched or duplicate results")
    return matched


@mcp.tool()
def inspect_pdf_and_propose_splits(
    pdf_path: str,
    work_dir: str,
    reliable_pages: int = 60,
    overlap_pages: int = 1,
) -> dict[str, Any]:
    """Inspect an official PDF and return reliable/economical split plans.

    This tool does not submit anything to MinerU. The agent must present the
    plans to the user and obtain an explicit choice before calling
    confirm_split_plan.
    """
    info = inspect_pdf(pdf_path)
    plans = propose_split_plans(
        info,
        reliable_pages=reliable_pages,
        overlap=overlap_pages,
    )
    store = JobStore(work_dir)
    job = DocumentJob(
        job_id=f"reg2md-{uuid4().hex[:12]}",
        source=info,
        work_dir=str(Path(work_dir).resolve()),
        state=JobState.WAITING_SPLIT_CONFIRMATION,
    )
    store.save(job)
    store.append_event(
        {
            "event": "pdf_inspected",
            "job_id": job.job_id,
            "page_count": info.page_count,
            "source_sha256": info.sha256,
        }
    )
    return {
        "job_id": job.job_id,
        "source": info.model_dump(mode="json"),
        "plans": [plan.model_dump(mode="json") for plan in plans],
        "confirmation_required": True,
    }


@mcp.tool()
def confirm_split_plan(
    work_dir: str,
    plan: dict[str, Any],
) -> dict[str, Any]:
    """Confirm a user-selected plan and physically split the PDF."""
    store = JobStore(work_dir)
    job = store.load()
    if job.state != JobState.WAITING_SPLIT_CONFIRMATION:
        raise ValueError(f"Job is not waiting for confirmation: {job.state}")
    selected = SplitPlan.model_validate(plan)
    if selected.source_sha256 != job.source.sha256:
        raise ValueError("Split plan belongs to a different source PDF")
    selected.confirmed = True
    split_dir = Path(work_dir).resolve() / "batches" / "pdf"
    written = split_pdf(job.source.path, selected.batches, split_dir)
    selected.batches = written
    updated = store.transition(
        JobState.SPLIT_CONFIRMED,
        split_plan=selected,
    )
    store.append_event(
        {
            "event": "split_confirmed",
            "job_id": updated.job_id,
            "plan": selected.name,
            "batch_count": len(written),
        }
    )
    return {
        "job_id": updated.job_id,
        "state": updated.state.value,
        "batches": [batch.model_dump(mode="json") for batch in written],
    }


@mcp.tool()
def submit_confirmed_batches_to_mineru(
    work_dir: str,
    model_version: str = "vlm",
    language: str = "latin",
    is_ocr: bool = False,
) -> dict[str, Any]:
    """Upload confirmed PDF batches to the official MinerU Precision API."""
    store = JobStore(work_dir)
    job = store.load()
    if job.state != JobState.SPLIT_CONFIRMED or job.split_plan is None:
        raise ValueError("A split plan must be confirmed before MinerU submission")
    with MinerUClient() as client:
        batch_ids = []
        for offset in range(0, len(job.split_plan.batches), 50):
            batch_ids.append(
                client.submit_files(
                    job.split_plan.batches[offset : offset + 50],
                    model_version=model_version,
                    language=language,
                    is_ocr=is_ocr,
                )
            )
    updated = store.transition(
        JobState.MINERU_RUNNING,
        mineru_batch_ids=batch_ids,
    )
    store.append_event(
        {
            "event": "mineru_submitted",
            "job_id": updated.job_id,
            "batch_ids": batch_ids,
        }
    )
    return {
        "job_id": updated.job_id,
        "state": updated.state.value,
        "mineru_batch_ids": batch_ids,
    }


@mcp.tool()
def mineru_batch_status(work_dir: str) -> dict[str, Any]:
    """Return current MinerU status so long jobs can be resumed."""
    store = JobStore(work_dir)
    job = store.load()
    if not job.mineru_batch_ids:
        raise ValueError("Job has no MinerU batch IDs")
    with MinerUClient() as client:
        batches = [
            {
                "batch_id": batch_id,
                "results": [
                    result.model_dump(mode="json")
                    for result in client.batch_status(batch_id)
                ],
            }
            for batch_id in job.mineru_batch_ids
        ]
    return {
        "job_id": job.job_id,
        "batches": batches,
    }


@mcp.tool()
def wait_for_and_download_mineru(
    work_dir: str,
    timeout_seconds: float = 3600,
) -> dict[str, Any]:
    """Wait for MinerU completion, download ZIPs, and preserve raw outputs."""
    store = JobStore(work_dir)
    job = store.load()
    if not job.mineru_batch_ids:
        raise ValueError("Job has no MinerU batch IDs")
    raw_dir = Path(work_dir).resolve() / "batches" / "mineru-raw"
    downloaded_results: list[dict[str, str | None]] = []
    with MinerUClient() as client:
        for index, batch_id in enumerate(job.mineru_batch_ids, start=1):
            results = client.wait_for_batch(
                batch_id,
                timeout_seconds=timeout_seconds,
            )
            start = (index - 1) * 50
            expected = (
                job.split_plan.batches[start : start + 50] if job.split_plan else []
            )
            results = _match_results_to_batches(results, expected)
            downloaded_results.extend(
                client.download_results(results, raw_dir / f"group-{index:03d}")
            )
    store.transition(JobState.MINERU_COMPLETED)
    store.append_event(
        {
            "event": "mineru_downloaded",
            "job_id": job.job_id,
            "results": downloaded_results,
        }
    )
    return {
        "job_id": job.job_id,
        "state": JobState.MINERU_COMPLETED.value,
        "results": downloaded_results,
    }


@mcp.tool()
def locate_mineru_output(directory: str, work_dir: str) -> dict[str, str]:
    """Locate MinerU Markdown and content_list.json in an extracted ZIP."""
    return find_mineru_files(
        within_work_dir(directory, work_dir, label="MinerU result directory")
    )


@mcp.tool()
def render_official_pdf_pages(
    pdf_path: str,
    pages: list[int],
    output_dir: str,
    work_dir: str,
    dpi: int = 150,
) -> dict[str, Any]:
    """Render official PDF pages to PNG for layout-sensitive AI review."""
    safe_output = within_work_dir(output_dir, work_dir, label="render output")
    rendered = render_pdf_pages(pdf_path, pages, safe_output, dpi=dpi)
    return {
        "pdf_path": str(Path(pdf_path).resolve()),
        "pages": sorted(set(pages)),
        "rendered_files": rendered,
        "dpi": dpi,
    }


@mcp.tool()
def update_job_stage(
    work_dir: str,
    stage: str,
    error: str | None = None,
) -> dict[str, Any]:
    """Persist an auditable workflow stage for resume and progress reporting."""
    state = JobState(stage)
    store = JobStore(work_dir)
    updated = store.transition(state, error=error)
    store.append_event(
        {
            "event": "stage_updated",
            "job_id": updated.job_id,
            "state": updated.state.value,
            "error": updated.error,
        }
    )
    return {
        "job_id": updated.job_id,
        "state": updated.state.value,
        "updated_at": updated.updated_at.isoformat(),
        "error": updated.error,
    }


@mcp.tool()
def initialize_ai_audit(
    source_pdf_path: str,
    markdown_path: str,
    manifest_path: str,
    work_dir: str,
    window_size: int = 20,
) -> dict[str, Any]:
    """Create page windows that must be audited and independently verified."""
    safe_markdown = within_work_dir(markdown_path, work_dir, label="Markdown")
    safe_manifest = within_work_dir(manifest_path, work_dir, label="audit manifest")
    manifest = initialize_audit_manifest(
        source_pdf_path,
        safe_markdown,
        safe_manifest,
        window_size=window_size,
    )
    return manifest.model_dump(mode="json")


@mcp.tool()
def record_ai_review_window(
    manifest_path: str,
    work_dir: str,
    start_page: int,
    end_page: int,
    stage: str,
    status: str,
    notes: str | None = None,
    markdown_path: str | None = None,
) -> dict[str, Any]:
    """Record one completed/needs-review audit or verification window."""
    safe_manifest = within_work_dir(manifest_path, work_dir, label="audit manifest")
    safe_markdown = (
        within_work_dir(markdown_path, work_dir, label="final Markdown")
        if markdown_path
        else None
    )
    manifest = record_audit_window(
        safe_manifest,
        start_page,
        end_page,
        stage,  # type: ignore[arg-type]
        ReviewWindowStatus(status),
        notes,
        safe_markdown,
    )
    return manifest.model_dump(mode="json")


@mcp.tool()
def normalize_mineru_batch(
    markdown_path: str,
    content_list_path: str,
    official_start_page: int,
    output_path: str,
    work_dir: str,
) -> dict[str, Any]:
    """Apply deterministic formatting and page markers without changing text."""
    return normalize_batch(
        within_work_dir(markdown_path, work_dir, label="MinerU Markdown"),
        within_work_dir(content_list_path, work_dir, label="MinerU content list"),
        official_start_page,
        within_work_dir(output_path, work_dir, label="normalized output"),
    )


@mcp.tool()
def merge_normalized_batches(
    batch_specs: list[dict[str, Any]],
    output_path: str,
    expected_page_count: int,
    work_dir: str,
) -> dict[str, Any]:
    """Verify overlap pages and merge normalized batches in source order."""
    safe_specs = []
    for spec in batch_specs:
        safe_spec = dict(spec)
        safe_spec["path"] = str(
            within_work_dir(spec["path"], work_dir, label="normalized batch")
        )
        safe_specs.append(safe_spec)
    result = merge_batches(
        safe_specs,
        within_work_dir(output_path, work_dir, label="merged output"),
        expected_page_count,
    )
    JobStore(work_dir).transition(JobState.NORMALIZED)
    return result


@mcp.tool()
def apply_source_verified_repairs(
    markdown_path: str,
    findings_path: str,
    output_path: str,
    work_dir: str,
    minimum_confidence: float = 0.95,
) -> dict[str, object]:
    """Apply only user-approved, source-verified findings with exact anchors."""
    return apply_approved_repairs(
        within_work_dir(markdown_path, work_dir, label="Markdown"),
        within_work_dir(findings_path, work_dir, label="findings"),
        within_work_dir(output_path, work_dir, label="repaired output"),
        minimum_confidence=minimum_confidence,
    )


@mcp.tool()
def validate_and_write_report(
    markdown_path: str,
    source_pdf_path: str,
    report_path: str,
    work_dir: str,
    findings_path: str | None = None,
    audit_manifest_path: str | None = None,
) -> dict[str, Any]:
    """Run release gates and write the human/machine-readable Markdown report."""
    safe_markdown = within_work_dir(markdown_path, work_dir, label="final Markdown")
    safe_report = within_work_dir(report_path, work_dir, label="validation report")
    safe_findings = (
        within_work_dir(findings_path, work_dir, label="findings")
        if findings_path
        else None
    )
    safe_manifest = (
        within_work_dir(audit_manifest_path, work_dir, label="audit manifest")
        if audit_manifest_path
        else None
    )
    result = validate_document(
        safe_markdown,
        source_pdf_path,
        safe_findings,
        safe_manifest,
    )
    written = write_validation_report(result, safe_report, safe_findings)
    store = JobStore(work_dir)
    if result.status == "passed":
        store.transition(JobState.VALIDATED)
    elif result.status == "needs_review":
        store.transition(JobState.NEEDS_HUMAN_REVIEW)
    else:
        store.transition(JobState.FAILED, error="Release validation failed")
    return {
        "validation": result.model_dump(mode="json"),
        "report_path": written,
        "release_allowed": result.status == "passed",
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
