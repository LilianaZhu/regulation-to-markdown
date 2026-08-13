# GitHub release checklist

## Before release

1. Update the version in:
   - `plugin.json`
   - `.claude-plugin/plugin.json`
   - `.claude-plugin/marketplace.json`
   - `pyproject.toml`
   - `src/regulation_to_markdown/__init__.py`
2. Update `CHANGELOG.md`.
3. Run:

   ```powershell
   python -m pytest
   python -m ruff check .
   python -m ruff format --check .
   claude plugin validate .
   ```

4. Run a clean Windows installation test.
   - `claude --plugin-dir .`
   - local marketplace add/install
   - MinerU Token secure user configuration
   - first-run Python runtime bootstrap under plugin data
5. Test a short text PDF, a PDF over 200 pages, a scanned PDF, a cross-page
   table, and missing MinerU image output.
6. Test visual-content policy cases:
   - a provision-related diagram is described and produces `needs_review`;
   - a human-reviewed diagram description can pass validation;
   - logos, coats of arms, signature-verification QR codes, handwritten
     signatures, and seals can be omitted with an informational report entry;
   - an unclassified image finding blocks release.
7. Confirm no token, signed URL, local path, PDF, ZIP, task state, or audit
   evidence is tracked by Git.
8. Confirm `plugin.json` validates against Agent Plugins 1.0.0.

## Release

1. Merge the reviewed changes into `main`.
2. Create a signed or annotated version tag.
3. Create a GitHub release using the matching `CHANGELOG.md` entry.
4. Share:

   <https://github.com/LilianaZhu/regulation-to-markdown>

The repository is both an Agent Plugin package and a Claude marketplace. Users
can add the GitHub or GitLab repository with `/plugin marketplace add`.
