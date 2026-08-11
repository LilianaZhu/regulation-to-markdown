from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    if sys.version_info < (3, 11):  # noqa: UP036 - bootstrap runs before install
        print("Python 3.11 or newer is required.", file=sys.stderr)
        return 1

    plugin_root = Path(__file__).resolve().parents[3]
    pyproject = plugin_root / "pyproject.toml"
    if not pyproject.is_file():
        print(f"Cannot find plugin pyproject.toml at {plugin_root}", file=sys.stderr)
        return 1

    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--user",
        "--upgrade",
        str(plugin_root),
    ]
    completed = subprocess.run(command, check=False)
    if completed.returncode == 0:
        print("Regulation to Markdown Python package installed.")
        print("Reload Cursor to start the local MCP server.")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
