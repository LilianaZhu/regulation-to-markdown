from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pymupdf
from pypdf import PdfReader, PdfWriter

from .models import PageBatch, PDFInfo, SplitPlan

MINERU_MAX_BYTES = 200 * 1024 * 1024
MINERU_MAX_PAGES = 200


class PDFError(RuntimeError):
    pass


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_pdf(path: str | Path) -> PDFInfo:
    pdf_path = Path(path).resolve()
    if not pdf_path.is_file():
        raise PDFError(f"PDF does not exist: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise PDFError("Only PDF input is supported")

    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:
        raise PDFError(f"Cannot read PDF: {exc}") from exc

    encrypted = bool(reader.is_encrypted)
    if encrypted:
        try:
            decrypted = reader.decrypt("")
            if not decrypted:
                raise PDFError("Encrypted PDF requires decryption before processing")
        except PDFError:
            raise
        except Exception as exc:
            raise PDFError(
                "Encrypted PDF requires decryption before processing"
            ) from exc

    page_count = len(reader.pages)
    if page_count == 0:
        raise PDFError("PDF contains no pages")

    sample_count = min(10, page_count)
    indexes = sorted(
        {
            round(i * (page_count - 1) / max(1, sample_count - 1))
            for i in range(sample_count)
        }
    )
    has_text_layer = False
    for index in indexes:
        try:
            if (reader.pages[index].extract_text() or "").strip():
                has_text_layer = True
                break
        except (KeyError, TypeError, ValueError):
            continue

    return PDFInfo(
        path=str(pdf_path),
        file_name=pdf_path.name,
        size_bytes=pdf_path.stat().st_size,
        page_count=page_count,
        sha256=sha256_file(pdf_path),
        encrypted=encrypted,
        has_text_layer=has_text_layer,
    )


def _batch_ranges(page_count: int, target_pages: int, overlap: int) -> list[PageBatch]:
    if target_pages < 1:
        raise ValueError("target_pages must be positive")
    if overlap < 0 or overlap >= target_pages:
        raise ValueError("overlap must be non-negative and smaller than target_pages")

    batches: list[PageBatch] = []
    start = 1
    index = 1
    while start <= page_count:
        end = min(page_count, start + target_pages - 1)
        batches.append(
            PageBatch(
                index=index,
                start_page=start,
                end_page=end,
                overlap_with_previous=overlap if index > 1 else 0,
            )
        )
        if end == page_count:
            break
        start = end - overlap + 1
        index += 1
    return batches


def propose_split_plans(
    info: PDFInfo,
    reliable_pages: int = 60,
    overlap: int = 1,
    max_pages: int = MINERU_MAX_PAGES,
    max_bytes: int = MINERU_MAX_BYTES,
) -> list[SplitPlan]:
    average_page_bytes = max(1, math.ceil(info.size_bytes / info.page_count))
    size_limited_pages = max(2, int(max_bytes * 0.9 // average_page_bytes))
    hard_capacity = max(2, min(max_pages, size_limited_pages))

    reliable_capacity = min(reliable_pages, hard_capacity)
    economical_capacity = hard_capacity

    plans: list[SplitPlan] = []
    for name, capacity, description in (
        (
            "reliable",
            reliable_capacity,
            "Smaller batches for stronger page-level AI review.",
        ),
        (
            "economical",
            economical_capacity,
            "Largest safe batches to reduce MinerU task count.",
        ),
    ):
        batches = _batch_ranges(info.page_count, capacity, overlap)
        for batch in batches:
            batch.estimated_size_bytes = average_page_bytes * batch.page_count
            batch.data_id = f"{info.sha256[:12]}-batch-{batch.index:03d}"
        plans.append(
            SplitPlan(
                name=name,
                description=description,
                batches=batches,
                source_sha256=info.sha256,
                source_page_count=info.page_count,
                source_size_bytes=info.size_bytes,
            )
        )
    return plans


def split_pdf(
    source_path: str | Path,
    batches: list[PageBatch],
    output_dir: str | Path,
    max_bytes: int = MINERU_MAX_BYTES,
    max_pages: int = MINERU_MAX_PAGES,
) -> list[PageBatch]:
    source = Path(source_path).resolve()
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(source))
    page_count = len(reader.pages)

    written: list[PageBatch] = []
    for batch in batches:
        if batch.end_page > page_count:
            raise PDFError(
                f"Batch {batch.index} ends at page {batch.end_page}, "
                f"but source has {page_count} pages"
            )
        if batch.page_count > max_pages:
            raise PDFError(
                f"Batch {batch.index} has {batch.page_count} pages; maximum is {max_pages}"
            )

        writer = PdfWriter()
        for page_number in range(batch.start_page - 1, batch.end_page):
            writer.add_page(reader.pages[page_number])
        writer.add_metadata(
            {
                "/Reg2MdSource": source.name,
                "/Reg2MdPageRange": f"{batch.start_page}-{batch.end_page}",
            }
        )

        output_path = destination / (
            f"{source.stem}.pages-{batch.start_page:04d}-{batch.end_page:04d}.pdf"
        )
        with output_path.open("wb") as handle:
            writer.write(handle)

        size = output_path.stat().st_size
        if size > max_bytes:
            output_path.unlink(missing_ok=True)
            raise PDFError(
                f"Batch {batch.index} is {size} bytes after splitting; "
                f"reduce batch size below the {max_bytes}-byte MinerU limit"
            )

        updated = batch.model_copy(
            update={
                "file_path": str(output_path),
                "estimated_size_bytes": size,
            }
        )
        written.append(updated)
    return written


def render_pdf_pages(
    source_path: str | Path,
    pages: list[int],
    output_dir: str | Path,
    *,
    dpi: int = 150,
) -> list[str]:
    if not pages:
        raise PDFError("At least one page is required")
    if dpi < 72 or dpi > 300:
        raise PDFError("dpi must be between 72 and 300")

    source = Path(source_path).resolve()
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    rendered: list[str] = []
    scale = dpi / 72
    matrix = pymupdf.Matrix(scale, scale)

    try:
        with pymupdf.open(source) as document:
            for page_number in sorted(set(pages)):
                if page_number < 1 or page_number > document.page_count:
                    raise PDFError(
                        f"Page {page_number} is outside 1-{document.page_count}"
                    )
                page = document.load_page(page_number - 1)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                output = destination / f"page-{page_number:04d}.png"
                pixmap.save(output)
                rendered.append(str(output))
    except PDFError:
        raise
    except Exception as exc:
        raise PDFError(f"Cannot render PDF pages: {exc}") from exc
    return rendered
