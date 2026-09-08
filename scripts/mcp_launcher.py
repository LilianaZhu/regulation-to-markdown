from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import venv
from contextlib import contextmanager
from pathlib import Path

_INSTALL_SECRET_NAMES = (
    "MINERU_API_TOKEN",
    "CLAUDE_PLUGIN_OPTION_MINERU_API_TOKEN",
)
_HOST_TEMPLATE_ENV = (
    "REG2MD_PLUGIN_ROOT",
    "REG2MD_PLUGIN_DATA",
    "CLAUDE_PLUGIN_ROOT",
    "CLAUDE_PLUGIN_DATA",
    "PLUGIN_ROOT",
    "PLUGIN_DATA",
    *_INSTALL_SECRET_NAMES,
)
_UNRESOLVED_TEMPLATE = re.compile(r"\$\{[^}]+\}")


def _has_unresolved_template(value: str | None) -> bool:
    return bool(value and _UNRESOLVED_TEMPLATE.search(value))


def _omit_unresolved_templates(env: dict[str, str]) -> dict[str, str]:
    cleaned = dict(env)
    for name in _HOST_TEMPLATE_ENV:
        if _has_unresolved_template(cleaned.get(name)):
            del cleaned[name]
    return cleaned


def _configured_path(value: str | None) -> Path | None:
    if not value or _has_unresolved_template(value):
        return None
    return Path(value).expanduser().resolve()


@contextmanager
def _without_install_secrets():
    removed = {
        name: os.environ.pop(name)
        for name in _INSTALL_SECRET_NAMES
        if name in os.environ
    }
    try:
        yield
    finally:
        os.environ.update(removed)


def _plugin_root(explicit: str | None = None) -> Path:
    for candidate in (explicit, os.environ.get("REG2MD_PLUGIN_ROOT")):
        path = _configured_path(candidate)
        if path is not None and (path / "pyproject.toml").is_file():
            return path
    return Path(__file__).resolve().parents[1]


def _plugin_data(explicit: str | None = None) -> Path:
    for candidate in (explicit, os.environ.get("REG2MD_PLUGIN_DATA")):
        path = _configured_path(candidate)
        if path is not None:
            path.mkdir(parents=True, exist_ok=True)
            return path
    data = Path.home() / ".regulation-to-markdown"
    data.mkdir(parents=True, exist_ok=True)
    return data


def _runtime_python(runtime: Path) -> Path:
    return (
        runtime / "Scripts" / "python.exe"
        if os.name == "nt"
        else runtime / "bin" / "python"
    )


def _fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    inputs = [
        root / "pyproject.toml",
        root / "plugin.json",
        root / ".claude-plugin" / "plugin.json",
        *sorted((root / "src").rglob("*.py")),
    ]
    for path in inputs:
        if not path.is_file():
            continue
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _install(root: Path, data: Path) -> Path:
    runtime = data / "python-runtime"
    runtime_python = _runtime_python(runtime)
    marker = runtime / ".reg2md-fingerprint"
    fingerprint = _fingerprint(root)
    if (
        runtime_python.is_file()
        and marker.is_file()
        and marker.read_text(encoding="utf-8").strip() == fingerprint
    ):
        return runtime_python

    log = data / "bootstrap.log"
    with _without_install_secrets():
        if not runtime_python.is_file():
            venv.EnvBuilder(with_pip=True, clear=True).create(runtime)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"\nInstalling plugin fingerprint {fingerprint}\n")
            completed = subprocess.run(
                [
                    str(runtime_python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-input",
                    "--upgrade",
                    str(root),
                ],
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.STDOUT,
                env=_omit_unresolved_templates(os.environ.copy()),
                check=False,
            )
    if completed.returncode != 0:
        raise RuntimeError(f"Python bootstrap failed. See {log}")
    marker.write_text(fingerprint + "\n", encoding="utf-8")
    return runtime_python


def _runtime_environ() -> dict[str, str]:
    return _omit_unresolved_templates(os.environ.copy())


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--install-only", action="store_true")
    parser.add_argument("--plugin-root")
    parser.add_argument("--data-dir")
    args = parser.parse_args()

    try:
        runtime_python = _install(
            _plugin_root(args.plugin_root),
            _plugin_data(args.data_dir),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"regulation-to-markdown: {exc}", file=sys.stderr)
        return 1
    if args.install_only:
        return 0
    return subprocess.call(
        [str(runtime_python), "-m", "regulation_to_markdown.mcp_server"],
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        env=_runtime_environ(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
