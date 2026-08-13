from __future__ import annotations

import hashlib

import pytest

from regulation_to_markdown.export import ExportError, export_final_artifacts


def _write_report(path, final_path, *, passed: bool = True) -> None:
    status = "passed" if passed else "failed"
    release_allowed = "true" if passed else "false"
    final_hash = hashlib.sha256(final_path.read_bytes()).hexdigest()
    path.write_text(
        "\n".join(
            [
                "---",
                f"status: {status}",
                f"release_allowed: {release_allowed}",
                "files:",
                f"  final_markdown: {final_path.name}",
                f"final_sha256: {final_hash}",
                "---",
                "",
                "# 核验报告",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_export_release_approved_artifacts_to_selected_directory(tmp_path):
    work_dir = tmp_path / "work"
    destination = tmp_path / "selected-output"
    work_dir.mkdir()
    final = work_dir / "regulation_FINAL.md"
    report = work_dir / "validation-report.md"
    final.write_text("Final regulation.\n", encoding="utf-8")
    _write_report(report, final)

    result = export_final_artifacts(
        final,
        report,
        destination,
        work_dir,
    )

    assert result["destination_dir"] == str(destination.resolve())
    assert result["artifacts"] == {
        "regulation_FINAL.md": "exported",
        "validation-report.md": "exported",
    }
    assert (destination / final.name).read_text(encoding="utf-8") == (
        "Final regulation.\n"
    )
    assert (destination / report.name).is_file()


def test_export_is_idempotent_but_does_not_overwrite_different_file(tmp_path):
    work_dir = tmp_path / "work"
    destination = tmp_path / "selected-output"
    work_dir.mkdir()
    destination.mkdir()
    final = work_dir / "regulation_FINAL.md"
    report = work_dir / "validation-report.md"
    final.write_text("Final regulation.\n", encoding="utf-8")
    _write_report(report, final)

    export_final_artifacts(final, report, destination, work_dir)
    repeated = export_final_artifacts(final, report, destination, work_dir)
    assert set(repeated["artifacts"].values()) == {"already_present"}

    (destination / final.name).write_text("Older different file.\n", encoding="utf-8")
    with pytest.raises(ExportError, match="Refusing to overwrite"):
        export_final_artifacts(final, report, destination, work_dir)

    overwritten = export_final_artifacts(
        final,
        report,
        destination,
        work_dir,
        overwrite=True,
    )
    assert overwritten["artifacts"][final.name] == "exported"
    assert (destination / final.name).read_text(encoding="utf-8") == (
        "Final regulation.\n"
    )


def test_export_blocks_unreleased_artifacts(tmp_path):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    final = work_dir / "regulation_FINAL.md"
    report = work_dir / "validation-report.md"
    final.write_text("Unreleased regulation.\n", encoding="utf-8")
    _write_report(report, final, passed=False)

    with pytest.raises(ExportError, match="only after validation passes"):
        export_final_artifacts(
            final,
            report,
            tmp_path / "selected-output",
            work_dir,
        )


def test_export_blocks_final_file_changed_after_validation(tmp_path):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    final = work_dir / "regulation_FINAL.md"
    report = work_dir / "validation-report.md"
    final.write_text("Validated content.\n", encoding="utf-8")
    _write_report(report, final)
    final.write_text("Changed after validation.\n", encoding="utf-8")

    with pytest.raises(ExportError, match="final Markdown hash"):
        export_final_artifacts(
            final,
            report,
            tmp_path / "selected-output",
            work_dir,
        )
