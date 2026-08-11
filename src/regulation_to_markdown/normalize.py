from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class NormalizationError(RuntimeError):
    pass


MEANINGFUL_BLOCKS = {"text", "code", "image", "table"}


def normalize_visible_text(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"(?m)^#{1,6}\s+", "", text)
    text = re.sub(r"(?m)^```[^\n]*$", "", text)
    text = re.sub(r">\s+<", "><", text)
    return re.sub(r"\s+", " ", text).strip()


def _content_value(block: dict[str, Any]) -> str:
    kind = block.get("type")
    if kind == "text":
        return str(block.get("text") or "").strip()
    if kind == "code":
        body = block.get("code_body") or ""
        return (
            "\n".join(map(str, body)).strip()
            if isinstance(body, list)
            else str(body).strip()
        )
    if kind == "image":
        image_path = str(block.get("img_path") or "")
        return f"![]({image_path})" if image_path else ""
    if kind == "table":
        captions = block.get("table_caption") or []
        if captions:
            return str(captions[0]).strip()
        return str(block.get("table_body") or "").strip()
    return ""


def _table_ranges(blocks: list[dict[str, Any]]) -> dict[int, int]:
    table_blocks = [block for block in blocks if block.get("type") == "table"]
    ranges: dict[int, int] = {}
    for index, block in enumerate(table_blocks):
        if not block.get("table_body") and not block.get("table_caption"):
            continue
        start = int(block["page_idx"])
        end = start
        cursor = index + 1
        while cursor < len(table_blocks):
            next_block = table_blocks[cursor]
            if int(next_block["page_idx"]) != end + 1:
                break
            if next_block.get("table_body") or next_block.get("table_caption"):
                break
            end += 1
            cursor += 1
        if end > start:
            ranges[start] = end
    return ranges


def _insert_page_markers(
    markdown: str,
    blocks: list[dict[str, Any]],
    official_start_page: int,
) -> tuple[str, dict[str, Any]]:
    cursor = 0
    positions: dict[int, tuple[int, bool]] = {}
    unmatched: list[dict[str, Any]] = []

    for block in blocks:
        if block.get("type") not in MEANINGFUL_BLOCKS:
            continue
        value = _content_value(block)
        if not value:
            continue
        found = markdown.find(value, cursor)
        if found < 0:
            prefix = value[:80].strip()
            found = markdown.find(prefix, cursor) if prefix else -1
        if found < 0:
            unmatched.append(
                {
                    "local_page": int(block.get("page_idx", -1)) + 1,
                    "type": block.get("type"),
                    "sample": value[:160],
                }
            )
            continue

        local_page = int(block["page_idx"])
        if local_page not in positions:
            line_start = markdown.rfind("\n", 0, found) + 1
            prefix = markdown[line_start:found]
            at_line_start = not prefix.strip() or bool(
                re.fullmatch(r"#{1,6}\s*", prefix)
            )
            positions[local_page] = (
                line_start if at_line_start else found,
                not at_line_start,
            )
        cursor = found + len(value)

    table_ranges = _table_ranges(blocks)
    covered: set[int] = set()
    insertions: list[tuple[int, str]] = []
    for local_page, (position, inline) in sorted(positions.items()):
        if local_page in covered:
            continue
        if local_page in table_ranges:
            local_end = table_ranges[local_page]
            official_start = official_start_page + local_page
            official_end = official_start_page + local_end
            marker = f"<!-- pdf-pages: {official_start}-{official_end} -->"
            covered.update(range(local_page, local_end + 1))
        else:
            marker = f"<!-- pdf-page: {official_start_page + local_page} -->"
            covered.add(local_page)
        suffix = " " if inline else "\n\n"
        insertions.append((position, marker + suffix))

    for position, marker in sorted(insertions, reverse=True):
        markdown = markdown[:position] + marker + markdown[position:]

    local_pages = {int(block["page_idx"]) for block in blocks if "page_idx" in block}
    return markdown, {
        "marker_count": len(insertions),
        "covered_local_pages": len(covered),
        "missing_local_pages": sorted(local_pages - covered),
        "unmatched_blocks": unmatched,
    }


def _pretty_tables(markdown: str) -> str:
    def format_table(match: re.Match[str]) -> str:
        return re.sub(r">\s*<", ">\n<", match.group(0))

    return re.sub(
        r"<table>.*?</table>",
        format_table,
        markdown,
        flags=re.DOTALL,
    )


def _image_references(markdown: str, markdown_path: Path) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for match in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", markdown):
        target = match.group(2).strip()
        remote = bool(re.match(r"^(?:https?|data):", target, flags=re.IGNORECASE))
        exists = remote or (markdown_path.parent / target).is_file()
        references.append(
            {
                "alt": match.group(1),
                "target": target,
                "remote": remote,
                "exists": exists,
            }
        )
    return references


def normalize_batch(
    markdown_path: str | Path,
    content_list_path: str | Path,
    official_start_page: int,
    output_path: str | Path,
) -> dict[str, Any]:
    source_md = Path(markdown_path).resolve()
    source_json = Path(content_list_path).resolve()
    output = Path(output_path).resolve()
    if official_start_page < 1:
        raise NormalizationError("official_start_page must be at least 1")
    if not source_md.is_file() or not source_json.is_file():
        raise NormalizationError("MinerU Markdown and content_list.json are required")

    original = source_md.read_text(encoding="utf-8")
    try:
        blocks = json.loads(source_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise NormalizationError(f"Cannot read content list: {exc}") from exc
    if not isinstance(blocks, list):
        raise NormalizationError("content_list.json must contain a list")

    normalized = original.replace("\r\n", "\n").replace("\r", "\n")
    normalized, marker_report = _insert_page_markers(
        normalized,
        blocks,
        official_start_page,
    )
    normalized = _pretty_tables(normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip() + "\n"

    if normalize_visible_text(original) != normalize_visible_text(normalized):
        raise NormalizationError(
            "Deterministic normalization changed visible text; output was not written"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(normalized, encoding="utf-8", newline="\n")
    images = _image_references(normalized, output)
    return {
        "output_path": str(output),
        "visible_text_integrity": "passed",
        "page_markers": marker_report,
        "images": images,
        "broken_images": [item for item in images if not item["exists"]],
        "code_fence_count": len(re.findall(r"(?m)^```", normalized)),
        "table_count": len(re.findall(r"<table>", normalized)),
    }


def find_mineru_files(directory: str | Path) -> dict[str, str]:
    root = Path(directory).resolve()
    markdown_candidates = sorted(
        path for path in root.rglob("*.md") if path.name not in {"README.md"}
    )
    preferred_markdown = [
        path for path in markdown_candidates if path.name == "full.md"
    ]
    if preferred_markdown:
        markdown_candidates = preferred_markdown
    content_candidates = sorted(root.rglob("*_content_list.json"))
    if not content_candidates:
        content_candidates = sorted(
            path
            for path in root.rglob("content_list.json")
            if not path.name.endswith("_v2.json")
        )
    if not markdown_candidates or not content_candidates:
        raise NormalizationError(
            f"Cannot find MinerU Markdown and content list under {root}"
        )
    if len(markdown_candidates) != 1 or len(content_candidates) != 1:
        raise NormalizationError(
            "MinerU output must contain one unambiguous Markdown and content list; "
            f"found markdown={len(markdown_candidates)}, "
            f"content_list={len(content_candidates)} under {root}"
        )
    return {
        "markdown": str(markdown_candidates[0]),
        "content_list": str(content_candidates[0]),
    }
