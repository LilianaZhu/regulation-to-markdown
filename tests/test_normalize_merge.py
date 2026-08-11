from __future__ import annotations

import json

import pytest

from regulation_to_markdown.merge import MergeError, merge_batches
from regulation_to_markdown.normalize import (
    NormalizationError,
    find_mineru_files,
    normalize_batch,
)


def test_normalize_adds_page_markers_without_text_change(tmp_path):
    markdown = tmp_path / "raw.md"
    content = tmp_path / "content_list.json"
    output = tmp_path / "normalized.md"
    markdown.write_text(
        "# Title\n\nFirst page text.\n\nSecond page text.\n",
        encoding="utf-8",
    )
    content.write_text(
        json.dumps(
            [
                {"type": "text", "text": "Title", "page_idx": 0},
                {"type": "text", "text": "First page text.", "page_idx": 0},
                {"type": "text", "text": "Second page text.", "page_idx": 1},
            ]
        ),
        encoding="utf-8",
    )

    result = normalize_batch(markdown, content, 10, output)
    text = output.read_text(encoding="utf-8")

    assert result["visible_text_integrity"] == "passed"
    assert "<!-- pdf-page: 10 -->" in text
    assert "<!-- pdf-page: 11 -->" in text
    assert result["page_markers"]["missing_local_pages"] == []


def test_merge_verifies_overlap_and_removes_duplicate(tmp_path):
    batch_one = tmp_path / "batch-1.md"
    batch_two = tmp_path / "batch-2.md"
    output = tmp_path / "final.md"
    batch_one.write_text(
        "<!-- pdf-page: 1 -->\n\nPage one.\n\n<!-- pdf-page: 2 -->\n\nOverlap.\n",
        encoding="utf-8",
    )
    batch_two.write_text(
        "<!-- pdf-page: 2 -->\n\nOverlap.\n\n<!-- pdf-page: 3 -->\n\nPage three.\n",
        encoding="utf-8",
    )

    result = merge_batches(
        [
            {"path": str(batch_one), "start_page": 1, "end_page": 2},
            {"path": str(batch_two), "start_page": 2, "end_page": 3},
        ],
        output,
        3,
    )
    text = output.read_text(encoding="utf-8")

    assert result["page_count"] == 3
    assert result["overlaps_verified"] is True
    assert text.count("<!-- pdf-page: 2 -->") == 1
    assert "Page three." in text


def test_merge_blocks_different_overlap(tmp_path):
    batch_one = tmp_path / "batch-1.md"
    batch_two = tmp_path / "batch-2.md"
    batch_one.write_text(
        "<!-- pdf-page: 1 -->\n\nOne.\n\n<!-- pdf-page: 2 -->\n\nOfficial A.\n",
        encoding="utf-8",
    )
    batch_two.write_text(
        "<!-- pdf-page: 2 -->\n\nOfficial B.\n\n<!-- pdf-page: 3 -->\n\nThree.\n",
        encoding="utf-8",
    )

    with pytest.raises(MergeError, match="Overlap page 2 differs"):
        merge_batches(
            [
                {"path": str(batch_one), "start_page": 1, "end_page": 2},
                {"path": str(batch_two), "start_page": 2, "end_page": 3},
            ],
            tmp_path / "final.md",
            3,
        )


def test_normalize_keeps_cross_page_sentence_inline(tmp_path):
    markdown = tmp_path / "raw.md"
    content = tmp_path / "content_list.json"
    output = tmp_path / "normalized.md"
    markdown.write_text("First half continuation.\n", encoding="utf-8")
    content.write_text(
        json.dumps(
            [
                {"type": "text", "text": "First half ", "page_idx": 0},
                {"type": "text", "text": "continuation.", "page_idx": 1},
            ]
        ),
        encoding="utf-8",
    )

    normalize_batch(markdown, content, 1, output)
    text = output.read_text(encoding="utf-8")

    assert "First half <!-- pdf-page: 2 --> continuation." in text
    assert "<!-- pdf-page: 2 -->\n\ncontinuation." not in text


def test_find_mineru_files_rejects_ambiguous_outputs(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    (tmp_path / "one" / "full.md").write_text("one", encoding="utf-8")
    (tmp_path / "two" / "full.md").write_text("two", encoding="utf-8")
    (tmp_path / "one_content_list.json").write_text("[]", encoding="utf-8")

    with pytest.raises(NormalizationError, match="one unambiguous"):
        find_mineru_files(tmp_path)
