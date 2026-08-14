"""Source-grounded regulation PDF to Markdown tooling."""

from .models import Finding, PDFInfo, SplitPlan, ValidationResult
from .pdf import inspect_pdf, propose_split_plans
from .validate import validate_document

__all__ = [
    "Finding",
    "PDFInfo",
    "SplitPlan",
    "ValidationResult",
    "inspect_pdf",
    "propose_split_plans",
    "validate_document",
]

__version__ = "0.2.2"
