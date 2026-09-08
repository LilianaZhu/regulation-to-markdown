#!/usr/bin/env python3
"""One-command setup for regulation-to-markdown.

Builds the isolated Python runtime, stores the MinerU API token where every
host can reach it, and registers the MCP server with the coding agent.

Standard library only: this runs before the plugin's runtime exists.

    python scripts/setup.py                     # interactive, auto-detect hosts
    python scripts/setup.py --token <TOKEN>     # non-interactive
    python scripts/setup.py --host cursor       # register one host only
    python scripts/setup.py --print-config      # show the entry, write nothing
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

SERVER_NAME = "regulation-to-markdown"
CREDENTIALS_FILE_NAME = "credentials.json"
TOKEN_KEY = "mineru_api_token"
TOKEN_URL = "https://mineru.net/apiManage/token"

_UNRESOLVED_TEMPLATE = re.compile(r"\$\{[^}]+\}")

HOSTS = {
    "cursor": Path.home() / ".cursor" / "mcp.json",
    "claude": Path.home() / ".claude" / "mcp.json",
    "windsurf": Path.home() / ".codeium" / "windsurf" / "mcp_config.json",
}


class SetupError(RuntimeError):
    pass


def _usable(value: str | None) -> str:
    if not value or _UNRESOLVED_TEMPLATE.search(value):
        return ""
    return value.strip()


def plugin_root() -> Path:
    root = Path(__file__).resolve().parents[1]
    if not (root / "pyproject.toml").is_file():
        raise SetupError(f"Not a plugin checkout: {root}")
    return root


def plugin_data_dir(explicit: str | None = None) -> Path:
    for candidate in (explicit, os.environ.get("REG2MD_PLUGIN_DATA")):
        resolved = _usable(candidate)
        if resolved:
            return Path(resolved).expanduser().resolve()
    return Path.home() / ".regulation-to-markdown"


def build_runtime(root: Path, data: Path) -> None:
    launcher = root / "scripts" / "mcp_launcher.py"
    print(f"[1/3] Building the isolated Python runtime in {data}")
    print("      First run downloads dependencies and can take a few minutes.")
    completed = subprocess.run(
        [
            sys.executable,
            str(launcher),
            "--install-only",
            "--plugin-root",
            str(root),
            "--data-dir",
            str(data),
        ],
        check=False,
    )
    if completed.returncode != 0:
        raise SetupError(
            f"Runtime bootstrap failed. See {data / 'bootstrap.log'} for details."
        )
    print("      Runtime ready.")


def prompt_for_token() -> str:
    print()
    print(f"      Create a MinerU API token at {TOKEN_URL}")
    print("      The value is hidden while you type and is never echoed.")
    for _ in range(3):
        try:
            entered = getpass.getpass("      MinerU API token: ")
        except (EOFError, KeyboardInterrupt):
            raise SetupError("No token supplied; setup cancelled.") from None
        if _usable(entered):
            return entered.strip()
        print("      Empty value, please try again.")
    raise SetupError("No token supplied after three attempts.")


def store_token(token: str, data: Path) -> Path:
    data.mkdir(parents=True, exist_ok=True)
    path = data / CREDENTIALS_FILE_NAME

    payload: dict[str, object] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(existing, dict):
                payload = existing
        except (OSError, json.JSONDecodeError):
            payload = {}
    payload[TOKEN_KEY] = token

    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return path


def server_entry(root: Path, data: Path) -> dict[str, object]:
    """Absolute paths only.

    Hosts such as Cursor do not expand ${PLUGIN_ROOT}, so a templated command
    would never start. Pointing at the launcher rather than the runtime keeps
    the entry valid after `git pull`, because the launcher rebuilds the runtime
    whenever the sources change.
    """
    return {
        "type": "stdio",
        "command": sys.executable,
        "args": [str(root / "scripts" / "mcp_launcher.py")],
        "cwd": str(root),
        "env": {
            "REG2MD_PLUGIN_ROOT": str(root),
            "REG2MD_PLUGIN_DATA": str(data),
            "PYTHONUTF8": "1",
        },
    }


def register_host(config_path: Path, entry: dict[str, object]) -> str:
    config: dict[str, object] = {}
    raw = ""
    if config_path.is_file():
        # utf-8-sig: editors and PowerShell on Windows routinely leave a BOM,
        # which plain utf-8 decoding would reject as invalid JSON.
        raw = config_path.read_text(encoding="utf-8-sig")
        if raw.strip():
            try:
                loaded = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SetupError(
                    f"{config_path} is not valid JSON and was left untouched: {exc}"
                ) from exc
            if isinstance(loaded, dict):
                config = loaded

    servers = config.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    action = "updated" if SERVER_NAME in servers else "added"
    servers[SERVER_NAME] = entry
    config["mcpServers"] = servers

    config_path.parent.mkdir(parents=True, exist_ok=True)
    if raw:
        backup = config_path.with_suffix(config_path.suffix + ".reg2md-backup")
        backup.write_text(raw, encoding="utf-8")
    temporary = config_path.with_suffix(config_path.suffix + ".tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, config_path)
    return action


def detect_hosts() -> list[str]:
    return [name for name, path in HOSTS.items() if path.parent.is_dir()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install regulation-to-markdown and configure the MinerU token."
    )
    parser.add_argument("--token", help="MinerU API token; prompted if omitted.")
    parser.add_argument(
        "--host",
        action="append",
        choices=[*HOSTS, "all", "none"],
        help="Host to register. Repeatable. Defaults to every detected host.",
    )
    parser.add_argument("--data-dir", help="Override the plugin data directory.")
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print the MCP entry and exit without changing anything.",
    )
    parser.add_argument(
        "--skip-runtime",
        action="store_true",
        help="Do not build the Python runtime.",
    )
    args = parser.parse_args()

    try:
        root = plugin_root()
        data = plugin_data_dir(args.data_dir)

        if args.print_config:
            print(json.dumps({"mcpServers": {SERVER_NAME: server_entry(root, data)}}, indent=2))
            return 0

        if args.skip_runtime:
            print("[1/3] Skipping runtime build as requested.")
        else:
            build_runtime(root, data)

        print()
        print("[2/3] Storing the MinerU API token")
        token = _usable(args.token) or _usable(os.environ.get("MINERU_API_TOKEN"))
        if token:
            print("      Using the token supplied on the command line or environment.")
        else:
            token = prompt_for_token()
        credentials = store_token(token, data)
        print(f"      Saved to {credentials} with owner-only permissions.")
        print("      The server reads the token from this file, so it no longer")
        print("      depends on the host forwarding environment variables.")

        print()
        print("[3/3] Registering the MCP server")
        selected = args.host or ["all"]
        if "none" in selected:
            targets: list[str] = []
        elif "all" in selected:
            targets = detect_hosts()
        else:
            targets = list(dict.fromkeys(selected))

        if not targets:
            print("      No host registered. Add this entry manually:")
            print(json.dumps({"mcpServers": {SERVER_NAME: server_entry(root, data)}}, indent=2))
        for name in targets:
            action = register_host(HOSTS[name], server_entry(root, data))
            print(f"      {name}: {action} in {HOSTS[name]}")

        print()
        print("Setup complete.")
        if targets:
            print("Restart the agent, or run 'Developer: Reload Window' in Cursor,")
            print("so it picks up the new MCP server.")
        print(
            "If a host also auto-loads this plugin's own manifest, disable that copy "
            "to avoid two servers with the same name."
        )
    except SetupError as exc:
        print(f"setup: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
