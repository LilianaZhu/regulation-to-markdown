# GitHub release checklist

## Before release

1. Update the version in:
   - `.cursor-plugin/plugin.json`
   - `pyproject.toml`
   - `src/regulation_to_markdown/__init__.py`
2. Update `CHANGELOG.md`.
3. Run:

   ```powershell
   python -m pytest
   python -m ruff check .
   python -m ruff format --check .
   ```

4. Run a clean Windows installation test.
5. Test a short text PDF, a PDF over 200 pages, a scanned PDF, a cross-page
   table, and missing MinerU image output.
6. Confirm no token, signed URL, local path, PDF, ZIP, task state, or audit
   evidence is tracked by Git.

## Release

1. Merge the reviewed changes into `main`.
2. Create a signed or annotated version tag.
3. Create a GitHub release using the matching `CHANGELOG.md` entry.
4. Share:

   <https://github.com/Lilianablog/regulation-to-markdown>

This project is distributed directly from GitHub and is not submitted to the
Cursor Marketplace.
