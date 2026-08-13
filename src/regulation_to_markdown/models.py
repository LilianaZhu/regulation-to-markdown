from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class PDFInfo(BaseModel):
    path: str
    file_name: str
    size_bytes: int
    page_count: int
    sha256: str
    encrypted: bool
    has_text_layer: bool


class PageBatch(BaseModel):
    index: int
    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)
    overlap_with_previous: int = Field(default=0, ge=0)
    estimated_size_bytes: int | None = None
    file_path: str | None = None
    data_id: str | None = None

    @field_validator("end_page")
    @classmethod
    def end_not_before_start(cls, value: int, info: Any) -> int:
        start = info.data.get("start_page")
        if start is not None and value < start:
            raise ValueError("end_page must be greater than or equal to start_page")
        return value

    @property
    def page_count(self) -> int:
        return self.end_page - self.start_page + 1


class SplitPlan(BaseModel):
    name: Literal["reliable", "economical", "custom"]
    description: str
    batches: list[PageBatch]
    source_sha256: str
    source_page_count: int
    source_size_bytes: int
    confirmed: bool = False


class JobState(StrEnum):
    UPLOADED = "uploaded"
    WAITING_SPLIT_CONFIRMATION = "waiting_split_confirmation"
    SPLIT_CONFIRMED = "split_confirmed"
    MINERU_RUNNING = "mineru_running"
    MINERU_COMPLETED = "mineru_completed"
    NORMALIZED = "normalized"
    AI_AUDITING = "ai_auditing"
    AI_REPAIRING = "ai_repairing"
    AI_VERIFYING = "ai_verifying"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    VALIDATED = "validated"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentJob(BaseModel):
    job_id: str
    source: PDFInfo
    work_dir: str
    state: JobState = JobState.UPLOADED
    split_plan: SplitPlan | None = None
    mineru_batch_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    error: str | None = None


class MinerUResult(BaseModel):
    file_name: str
    state: str
    data_id: str | None = None
    full_zip_url: str | None = None
    err_msg: str | None = None
    extract_progress: dict[str, Any] | None = None


class FindingSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingStatus(StrEnum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"


class VisualClassification(StrEnum):
    MEANINGFUL = "meaningful"
    NON_SUBSTANTIVE = "non_substantive"


class VisualDisposition(StrEnum):
    DESCRIBED = "described"
    OMITTED = "omitted"
    PRESERVED = "preserved"


class ReviewWindowStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"


class AuditWindow(BaseModel):
    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)
    audit_status: ReviewWindowStatus = ReviewWindowStatus.PENDING
    verify_status: ReviewWindowStatus = ReviewWindowStatus.PENDING
    audit_notes: str | None = None
    verify_notes: str | None = None


class AuditManifest(BaseModel):
    schema_version: int = 1
    source_pdf_path: str
    source_sha256: str
    markdown_path: str
    markdown_sha256: str
    final_markdown_sha256: str | None = None
    page_count: int
    window_size: int
    windows: list[AuditWindow]
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Finding(BaseModel):
    finding_id: str
    stage: Literal["audit", "repair", "verify"] = "audit"
    category: str
    severity: FindingSeverity
    status: FindingStatus = FindingStatus.OPEN
    pdf_page: int = Field(ge=1)
    md_line_start: int | None = Field(default=None, ge=1)
    md_line_end: int | None = Field(default=None, ge=1)
    official_quote: str
    markdown_quote: str
    proposed_replacement: str | None = None
    rationale: str
    confidence: float = Field(ge=0, le=1)
    source_verified: bool = False
    reviewer_notes: str | None = None
    visual_classification: VisualClassification | None = None
    visual_disposition: VisualDisposition | None = None
    visual_description: str | None = None
    human_review_required: bool = False
    human_reviewed: bool = False


class ValidationCheck(BaseModel):
    check_id: str
    title: str
    status: Literal["pass", "warning", "fail"]
    detail: str
    blocking: bool = False


class ValidationResult(BaseModel):
    document_path: str
    source_pdf_path: str
    source_sha256: str
    status: Literal["passed", "needs_review", "failed"]
    generated_at: datetime = Field(default_factory=utc_now)
    page_count: int
    covered_pages: int
    table_count: int
    findings_total: int
    unresolved_high_findings: int
    checks: list[ValidationCheck]
    notes: list[str] = Field(default_factory=list)


def path_string(path: str | Path) -> str:
    return str(Path(path).resolve())
