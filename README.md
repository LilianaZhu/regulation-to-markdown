# Regulation to Markdown

[中文使用说明](README.zh-CN.md)

A Cursor Plugin for converting official regulation PDFs and other authoritative
documents into source-grounded Markdown.

The plugin combines:

- the official MinerU Precision API for extraction;
- local Python for deterministic PDF splitting, normalization, merging, and
  validation;
- Cursor Agent for source comparison, source-grounded repair, and independent
  verification.

It does not assume Indonesian BAB/Pasal structure. Agent detects the structure
used by each source document.

## What the team member does

1. Put the official PDF in a local Cursor workspace.
2. Run `/regulation-to-markdown @document.pdf`, or ask Agent:
   `Use regulation-to-markdown on @document.pdf`.
3. Choose Reliable or Economical when Cursor displays the split plan.
4. Wait for MinerU extraction.
5. Review any high-risk source repairs when Agent asks.
6. Receive:
   - `<document>_FINAL.md`;
   - `validation-report.md`.

The regulation knowledge base should ingest only `FINAL.md`. The validation
report is retained as an audit record.

## Safety model

- MinerU output is not treated as authoritative.
- Python formatting may not change the visible text stream.
- AI audit does not edit files.
- Legal wording changes require an exact PDF page, source quote, explicit
  approval, and independent verification.
- Official-source typos are preserved rather than silently corrected.
- A failed release gate blocks `FINAL.md`.

## MinerU limits used by the plugin

The plugin applies the conservative limits documented for the MinerU Precision
API:

- maximum 200 MB per uploaded file;
- maximum 200 pages per file;
- maximum 50 signed upload URLs per request.

Long PDFs are physically split with one-page overlap. Indonesian and other
Latin-script documents default to `language=latin`.

MinerU API reference: <https://mineru.net/apiManage/docs>

## Install from GitHub with Cursor

This repository is distributed directly from GitHub and is not submitted to the
Cursor Marketplace. Give Cursor Agent this prompt:

```text
Review and install this Cursor Plugin for me:
https://github.com/LilianaZhu/regulation-to-markdown

Before installation, confirm that no secret is hard-coded. On Windows, clone the
repository and run install.ps1 with -InstallLocalPlugin. Ask for my approval
before executing commands. Do not send any PDF to MinerU until I explicitly
confirm a split plan.
```

Cursor must ask before cloning or running the installer. A GitHub link is not a
silent-install mechanism.

## Manual installation on Windows

Requirements:

- Cursor with Plugin, Skill, and MCP support;
- Python 3.11 or newer available as `python`;
- internet access;
- a MinerU Precision API token.

From PowerShell:

```powershell
git clone https://github.com/LilianaZhu/regulation-to-markdown.git
Set-Location .\regulation-to-markdown
powershell -ExecutionPolicy Bypass -File .\install.ps1 -InstallLocalPlugin
```

Then reload Cursor and open **Customize**. Configure `MINERU_API_TOKEN` for the
plugin. Never paste the token into chat or commit it to Git.

If the plugin files were copied without running the installer, the first
`/regulation-to-markdown` run detects whether the Python package is missing.
With user permission, Agent runs the Skill-local `scripts/bootstrap.py`; reload
Cursor once afterwards.
Cursor plugins do not automatically install `requirements.txt`.

### Update

```powershell
Set-Location .\regulation-to-markdown
git pull
powershell -ExecutionPolicy Bypass -File .\install.ps1 -InstallLocalPlugin
```

Reload Cursor after updating.

### Uninstall

```powershell
Remove-Item -Recurse -Force "$HOME\.cursor\plugins\local\regulation-to-markdown"
python -m pip uninstall regulation-to-markdown
```

For contributors:

```powershell
.\install.ps1 -Dev -InstallLocalPlugin
python -m pytest
```

## Development layout

```text
.cursor-plugin/plugin.json          Cursor Plugin manifest
skills/regulation-to-markdown/      Agent workflow and review rules
commands/regulation-to-markdown.md  Explicit conversion command
mcp.json                            Local stdio MCP configuration
src/regulation_to_markdown/         Python implementation
tests/                              Unit and mocked API tests
install.ps1                         Windows installer
```

## MCP tools

- `inspect_pdf_and_propose_splits`
- `confirm_split_plan`
- `submit_confirmed_batches_to_mineru`
- `mineru_batch_status`
- `wait_for_and_download_mineru`
- `locate_mineru_output`
- `render_official_pdf_pages`
- `update_job_stage`
- `initialize_ai_audit`
- `record_ai_review_window`
- `normalize_mineru_batch`
- `merge_normalized_batches`
- `apply_source_verified_repairs`
- `validate_and_write_report`

The first tool only proposes plans. Submission is technically blocked until
`confirm_split_plan` is called after user confirmation.

## Job files

Each document gets a dedicated work directory:

```text
work/<job-id>/
├── job.json
├── events.jsonl
├── batches/
│   ├── pdf/
│   ├── mineru-raw/
│   └── normalized/
├── findings.jsonl
├── audit-manifest.json
├── repairs/
├── FINAL.md
└── validation-report.md
```

Raw files are immutable evidence. Do not place `work/` under version control.

## Distribution

Share this public repository URL:

<https://github.com/LilianaZhu/regulation-to-markdown>

Recipients can give the URL to Cursor Agent using the reviewed-install prompt
above, or clone and run the installer manually. No Marketplace submission is
required.

Official references:

- <https://cursor.com/docs/plugins>
- <https://cursor.com/docs/reference/plugins>
- <https://cursor.com/docs/skills>
- <https://cursor.com/docs/mcp>

Release checklist: [docs/GITHUB_RELEASE.md](docs/GITHUB_RELEASE.md)

## Current scope

This first version provides the local processing engine, MinerU client, MCP
tools, Agent workflow, source-repair protocol, validation report, and tests.

It intentionally does not run an unattended external AI API. Cursor Agent is
the AI review layer while the user is in Cursor. The Python package remains
usable if a replaceable AI adapter is added later.
