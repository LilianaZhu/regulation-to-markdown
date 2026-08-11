from __future__ import annotations

from pathlib import Path

from regulation_to_markdown.models import PDFInfo
from regulation_to_markdown.pdf import (
    inspect_pdf,
    propose_split_plans,
    render_pdf_pages,
    split_pdf,
)


def test_propose_and_split_long_pdf(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "long.pdf", 217)
    info = inspect_pdf(source)

    assert info.page_count == 217
    assert info.has_text_layer is False
    assert len(info.sha256) == 64

    reliable, economical = propose_split_plans(info, reliable_pages=60, overlap=1)
    assert reliable.name == "reliable"
    assert reliable.batches[0].start_page == 1
    assert reliable.batches[0].end_page == 60
    assert reliable.batches[1].start_page == 60
    assert reliable.batches[-1].end_page == 217
    assert economical.batches[0].page_count <= 200

    written = split_pdf(source, reliable.batches, tmp_path / "split")
    assert len(written) == len(reliable.batches)
    assert all(batch.file_path for batch in written)
    assert all(batch.page_count <= 200 for batch in written)


def test_economical_plan_respects_200_page_limit():
    info = PDFInfo(
        path="source.pdf",
        file_name="source.pdf",
        size_bytes=10 * 1024 * 1024,
        page_count=201,
        sha256="a" * 64,
        encrypted=False,
        has_text_layer=True,
    )

    economical = propose_split_plans(info)[1]

    assert economical.batches[0].start_page == 1
    assert economical.batches[0].end_page == 200
    assert economical.batches[1].start_page == 200
    assert economical.batches[1].end_page == 201


def test_render_official_pages_for_visual_review(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "source.pdf", 2)

    rendered = render_pdf_pages(source, [2, 1, 2], tmp_path / "images", dpi=72)

    assert [path.split("page-")[-1] for path in rendered] == [
        "0001.png",
        "0002.png",
    ]
    assert all(Path(path).read_bytes().startswith(b"\x89PNG") for path in rendered)
