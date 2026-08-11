from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .normalize import normalize_visible_text

MARKER_PATTERN = re.compile(r"<!-- pdf-page: (\d+) -->|<!-- pdf-pages: (\d+)-(\d+) -->")


class MergeError(RuntimeError):
    pass


def _marker_pages(match: re.Match[str]) -> set[int]:
    if match.group(1):
        return {int(match.group(1))}
    return set(range(int(match.group(2)), int(match.group(3)) + 1))


def page_segments(markdown: str) -> dict[int, str]:
    markers = list(MARKER_PATTERN.finditer(markdown))
    segments: dict[int, str] = {}
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(markdown)
        content = markdown[marker.start() : end]
        pages = _marker_pages(marker)
        for page in pages:
            if page in segments:
                raise MergeError(f"Page {page} appears more than once in one batch")
            segments[page] = content
    return segments


def covered_pages(markdown: str) -> set[int]:
    pages: set[int] = set()
    for marker in MARKER_PATTERN.finditer(markdown):
        pages.update(_marker_pages(marker))
    return pages


def merge_batches(
    batch_specs: list[dict[str, Any]],
    output_path: str | Path,
    expected_page_count: int,
) -> dict[str, Any]:
    if not batch_specs:
        raise MergeError("No normalized batches supplied")
    if expected_page_count < 1:
        raise MergeError("expected_page_count must be positive")

    sorted_specs = sorted(batch_specs, key=lambda item: int(item["start_page"]))
    documents: list[tuple[dict[str, Any], str, dict[int, str]]] = []
    for spec in sorted_specs:
        path = Path(str(spec["path"])).resolve()
        if not path.is_file():
            raise MergeError(f"Normalized batch does not exist: {path}")
        text = path.read_text(encoding="utf-8")
        documents.append((spec, text, page_segments(text)))

    merged = documents[0][1].rstrip()
    merged_pages = covered_pages(merged)
    overlap_checks: list[dict[str, Any]] = []

    for spec, text, segments in documents[1:]:
        pages = set(segments)
        overlap = sorted(merged_pages & pages)
        for page in overlap:
            merged_segment = page_segments(merged).get(page)
            current_segment = segments[page]
            if merged_segment is None:
                raise MergeError(f"Cannot locate overlap page {page} in merged text")
            left = normalize_visible_text(merged_segment)
            right = normalize_visible_text(current_segment)
            identical = left == right
            overlap_checks.append({"page": page, "identical": identical})
            if not identical:
                raise MergeError(
                    f"Overlap page {page} differs between batches; "
                    "manual source review is required"
                )

        new_pages = sorted(pages - merged_pages)
        if not new_pages:
            continue
        first_new_page = new_pages[0]
        marker_match = None
        for marker in MARKER_PATTERN.finditer(text):
            if first_new_page in _marker_pages(marker):
                marker_match = marker
                break
        if marker_match is None:
            raise MergeError(f"Cannot find marker for page {first_new_page}")
        if len(_marker_pages(marker_match)) > 1 and overlap:
            raise MergeError(
                f"Page {first_new_page} shares a range marker across an overlap; "
                "split the table/page range manually before merging"
            )
        merged += "\n\n" + text[marker_match.start() :].strip()
        merged_pages.update(new_pages)

    expected_pages = set(range(1, expected_page_count + 1))
    if merged_pages != expected_pages:
        missing = sorted(expected_pages - merged_pages)
        extra = sorted(merged_pages - expected_pages)
        raise MergeError(f"Page coverage mismatch; missing={missing}, extra={extra}")

    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(merged.strip() + "\n", encoding="utf-8", newline="\n")
    return {
        "output_path": str(output),
        "page_count": len(merged_pages),
        "overlap_checks": overlap_checks,
        "overlaps_verified": all(item["identical"] for item in overlap_checks),
    }
