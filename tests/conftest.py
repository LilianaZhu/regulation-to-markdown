from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfWriter


@pytest.fixture
def make_pdf():
    def _make(path: Path, page_count: int) -> Path:
        writer = PdfWriter()
        for _ in range(page_count):
            writer.add_blank_page(width=612, height=792)
        with path.open("wb") as handle:
            writer.write(handle)
        return path

    return _make
