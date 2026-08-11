from __future__ import annotations

from pathlib import Path


class PathBoundaryError(ValueError):
    pass


def within_work_dir(
    path: str | Path,
    work_dir: str | Path,
    *,
    label: str = "path",
) -> Path:
    candidate = Path(path).resolve()
    root = Path(work_dir).resolve()
    if candidate != root and root not in candidate.parents:
        raise PathBoundaryError(f"{label} must stay inside work_dir: {candidate}")
    return candidate
