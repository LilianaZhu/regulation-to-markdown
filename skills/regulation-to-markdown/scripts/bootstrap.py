from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    if sys.version_info < (3, 11):  # noqa: UP036 - bootstrap runs before install
        print("Python 3.11 or newer is required.", file=sys.stderr)
        return 1

    plugin_root = Path(__file__).resolve().parents[3]
    launcher = plugin_root / "scripts" / "mcp_launcher.py"
    if not launcher.is_file():
        print(f"Cannot find MCP launcher at {launcher}", file=sys.stderr)
        return 1

    command = [
        sys.executable,
        str(launcher),
        "--install-only",
        "--plugin-root",
        str(plugin_root),
    ]
    completed = subprocess.run(command, check=False)
    if completed.returncode == 0:
        print("Regulation to Markdown Python runtime installed.")
        print("Reload the plugin or restart your agent client.")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
