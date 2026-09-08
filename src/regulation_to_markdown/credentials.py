"""Credential storage that does not depend on host environment inheritance.

Agent Plugins 1.0.0 does not define credential storage, and several hosts do
not forward inherited environment variables to stdio MCP servers. Reading the
token from a file the plugin owns keeps the token reachable on every host.
"""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

CREDENTIALS_FILE_NAME = "credentials.json"
TOKEN_KEY = "mineru_api_token"

_UNRESOLVED_TEMPLATE = re.compile(r"\$\{[^}]+\}")


def _usable(value: str | None) -> str:
    if not value or _UNRESOLVED_TEMPLATE.search(value):
        return ""
    return value.strip()


def plugin_data_dir(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the writable directory that holds the runtime and credentials."""
    for candidate in (explicit, os.environ.get("REG2MD_PLUGIN_DATA")):
        resolved = _usable(str(candidate)) if candidate is not None else ""
        if resolved:
            return Path(resolved).expanduser().resolve()
    return Path.home() / ".regulation-to-markdown"


def credentials_path(data_dir: str | os.PathLike[str] | None = None) -> Path:
    return plugin_data_dir(data_dir) / CREDENTIALS_FILE_NAME


def read_stored_token(data_dir: str | os.PathLike[str] | None = None) -> str:
    path = credentials_path(data_dir)
    if not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return _usable(payload.get(TOKEN_KEY))


def write_stored_token(
    token: str,
    data_dir: str | os.PathLike[str] | None = None,
) -> Path:
    cleaned = _usable(token)
    if not cleaned:
        raise ValueError("Refusing to store an empty or unresolved MinerU token")
    directory = plugin_data_dir(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / CREDENTIALS_FILE_NAME

    payload: dict[str, object] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(existing, dict):
                payload = existing
        except (OSError, json.JSONDecodeError):
            payload = {}
    payload[TOKEN_KEY] = cleaned

    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    _restrict_permissions(path)
    return path


def _restrict_permissions(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def resolve_token(
    explicit: str | None = None,
    data_dir: str | os.PathLike[str] | None = None,
) -> str:
    """Explicit argument, then host environment, then the stored credential."""
    return (
        _usable(explicit)
        or _usable(os.environ.get("MINERU_API_TOKEN"))
        or read_stored_token(data_dir)
    )
