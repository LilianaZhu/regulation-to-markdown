from __future__ import annotations

import json
import os
from pathlib import Path

from .models import DocumentJob, JobState, utc_now


class JobStore:
    def __init__(self, work_dir: str | Path):
        self.work_dir = Path(work_dir).resolve()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.work_dir / "job.json"

    def save(self, job: DocumentJob) -> DocumentJob:
        updated = job.model_copy(update={"updated_at": utc_now()})
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(
            updated.model_dump_json(indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
        return updated

    def load(self) -> DocumentJob:
        if not self.path.is_file():
            raise FileNotFoundError(f"Job state not found: {self.path}")
        return DocumentJob.model_validate_json(self.path.read_text(encoding="utf-8"))

    def transition(
        self,
        state: JobState,
        *,
        error: str | None = None,
        **updates: object,
    ) -> DocumentJob:
        job = self.load()
        allowed = ALLOWED_TRANSITIONS[job.state]
        if state not in allowed:
            raise ValueError(
                f"Invalid job transition: {job.state.value} -> {state.value}"
            )
        payload = {"state": state, "error": error, **updates}
        return self.save(job.model_copy(update=payload))

    def append_event(self, event: dict[str, object]) -> None:
        path = self.work_dir / "events.jsonl"
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


ALLOWED_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.UPLOADED: {JobState.WAITING_SPLIT_CONFIRMATION, JobState.FAILED},
    JobState.WAITING_SPLIT_CONFIRMATION: {
        JobState.SPLIT_CONFIRMED,
        JobState.FAILED,
    },
    JobState.SPLIT_CONFIRMED: {JobState.MINERU_RUNNING, JobState.FAILED},
    JobState.MINERU_RUNNING: {JobState.MINERU_COMPLETED, JobState.FAILED},
    JobState.MINERU_COMPLETED: {JobState.NORMALIZED, JobState.FAILED},
    JobState.NORMALIZED: {JobState.AI_AUDITING, JobState.FAILED},
    JobState.AI_AUDITING: {
        JobState.AI_REPAIRING,
        JobState.NEEDS_HUMAN_REVIEW,
        JobState.FAILED,
    },
    JobState.AI_REPAIRING: {
        JobState.AI_VERIFYING,
        JobState.NEEDS_HUMAN_REVIEW,
        JobState.FAILED,
    },
    JobState.AI_VERIFYING: {
        JobState.VALIDATED,
        JobState.NEEDS_HUMAN_REVIEW,
        JobState.FAILED,
    },
    JobState.NEEDS_HUMAN_REVIEW: {
        JobState.AI_AUDITING,
        JobState.AI_REPAIRING,
        JobState.AI_VERIFYING,
        JobState.FAILED,
    },
    JobState.VALIDATED: {
        JobState.COMPLETED,
        JobState.NEEDS_HUMAN_REVIEW,
        JobState.FAILED,
    },
    JobState.COMPLETED: set(),
    JobState.FAILED: set(),
}
