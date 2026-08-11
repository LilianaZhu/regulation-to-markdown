from __future__ import annotations

import pytest

from regulation_to_markdown.models import DocumentJob, JobState, PDFInfo
from regulation_to_markdown.paths import PathBoundaryError, within_work_dir
from regulation_to_markdown.state import JobStore


def _job(tmp_path, state: JobState) -> DocumentJob:
    return DocumentJob(
        job_id="reg2md-test",
        source=PDFInfo(
            path=str(tmp_path / "source.pdf"),
            file_name="source.pdf",
            size_bytes=1,
            page_count=1,
            sha256="0" * 64,
            encrypted=False,
            has_text_layer=True,
        ),
        work_dir=str(tmp_path),
        state=state,
    )


def test_path_boundary_rejects_output_outside_work_dir(tmp_path):
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    with pytest.raises(PathBoundaryError, match="inside work_dir"):
        within_work_dir(tmp_path / "outside.md", work_dir)


def test_job_state_rejects_skipping_validation(tmp_path):
    store = JobStore(tmp_path / "work")
    store.save(_job(tmp_path / "work", JobState.AI_VERIFYING))

    with pytest.raises(ValueError, match="ai_verifying -> completed"):
        store.transition(JobState.COMPLETED)


def test_job_state_allows_validation_then_completion(tmp_path):
    store = JobStore(tmp_path / "work")
    store.save(_job(tmp_path / "work", JobState.AI_VERIFYING))

    store.transition(JobState.VALIDATED)
    completed = store.transition(JobState.COMPLETED)

    assert completed.state == JobState.COMPLETED
