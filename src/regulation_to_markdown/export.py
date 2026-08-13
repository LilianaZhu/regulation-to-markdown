from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4

import yaml

from .paths import within_work_dir
from .pdf import sha256_file


class ExportError(RuntimeError):
    pass


def _report_metadata(report_path: Path) -> dict[str, object]:
    report = report_path.read_text(encoding="utf-8")
    parts = report.split("---", 2)
    if len(parts) != 3:
        raise ExportError("Validation report has no YAML frontmatter")
    metadata = yaml.safe_load(parts[1])
    if not isinstance(metadata, dict):
        raise ExportError("Validation report frontmatter must be a mapping")
    return metadata


def _copy_artifact(
    source: Path,
    destination: Path,
    *,
    overwrite: bool,
) -> str:
    if source == destination:
        return "already_present"
    if destination.exists():
        if not destination.is_file():
            raise ExportError(f"Export destination is not a file: {destination}")
        if sha256_file(source) == sha256_file(destination):
            return "already_present"
        if not overwrite:
            raise ExportError(
                f"Refusing to overwrite a different existing file: {destination}"
            )

    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.exporting")
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return "exported"


def export_final_artifacts(
    final_markdown_path: str | Path,
    report_path: str | Path,
    destination_dir: str | Path,
    work_dir: str | Path,
    *,
    overwrite: bool = False,
) -> dict[str, object]:
    """Export only release-approved deliverables to a user-selected directory."""
    final_markdown = within_work_dir(
        final_markdown_path,
        work_dir,
        label="final Markdown",
    )
    report = within_work_dir(
        report_path,
        work_dir,
        label="validation report",
    )
    for artifact in (final_markdown, report):
        if not artifact.is_file():
            raise ExportError(f"Export artifact not found: {artifact}")

    metadata = _report_metadata(report)
    if (
        metadata.get("status") != "passed"
        or metadata.get("release_allowed") is not True
    ):
        raise ExportError(
            "Final artifacts may be exported only after validation passes"
        )
    reported_final = metadata.get("files", {})
    if (
        not isinstance(reported_final, dict)
        or reported_final.get("final_markdown") != final_markdown.name
    ):
        raise ExportError(
            "Validation report does not reference the requested final Markdown"
        )
    if metadata.get("final_sha256") != sha256_file(final_markdown):
        raise ExportError(
            "Validation report does not match the requested final Markdown hash"
        )

    expanded_destination = Path(os.path.expandvars(str(destination_dir))).expanduser()
    if not expanded_destination.is_absolute():
        raise ExportError("Export destination must be an absolute directory path")
    destination = expanded_destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir():
        raise ExportError(f"Export destination is not a directory: {destination}")

    results: dict[str, str] = {}
    exported_paths: list[str] = []
    for source in (final_markdown, report):
        target = destination / source.name
        results[source.name] = _copy_artifact(
            source,
            target,
            overwrite=overwrite,
        )
        exported_paths.append(str(target))

    return {
        "destination_dir": str(destination),
        "artifacts": results,
        "exported_paths": exported_paths,
    }
