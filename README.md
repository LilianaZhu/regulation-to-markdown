# Regulation to Markdown

[中文使用说明](README.zh-CN.md)

A portable Agent Plugin for converting official regulation PDFs and other
authoritative documents into source-grounded Markdown.

It combines:

- the official MinerU Precision API for extraction;
- deterministic local Python for splitting, normalization, merging, evidence
  tracking, export, and release validation;
- an agent skill for page-by-page comparison, source-grounded repair, and
  independent verification.

The official PDF is always the legal source of truth.

## Package formats

This repository intentionally ships two compatible manifests:

- `plugin.json` — Agent Plugins 1.0.0 portable manifest;
- `.claude-plugin/plugin.json` — Claude Code/Desktop manifest with secure
  MinerU Token configuration.

The shared `skills/` directory and Python MCP implementation are the single
source package. Claude's installed cache and runtime under plugin data are
managed artifacts, not editable source copies.

## Install in Claude Code CLI

Requirements:

- Claude Code 2.1.207 or newer;
- Python 3.11 or newer available as `python`;
- network access to GitHub, PyPI, MinerU, and MinerU's signed upload/download
  hosts.

In an interactive Claude Code session, add this GitHub repository and install
the plugin:

```text
/plugin marketplace add LilianaZhu/regulation-to-markdown
/plugin install regulation-to-markdown@liliana-legal-tools
/reload-plugins
```

The install/enable flow opens Claude Code's configuration dialog. Paste the
MinerU API Token created at:

<https://mineru.net/apiManage/token>

The input is masked because the option is declared `sensitive`, and Claude Code
stores it in its credential mechanism instead of plaintext plugin settings.
Never paste the Token into chat, Git, job files, command history, or validation
reports.

To replace the Token later, open `/plugin`, select the plugin under
**Installed**, and use **Configure**.

On first activation, the plugin creates an isolated Python runtime in Claude's
persistent plugin-data directory and downloads the pinned dependencies from
PyPI. This can take several minutes. The launcher removes the MinerU Token from
the environment of `venv`, `pip`, and build subprocesses; only the final MCP
server receives it. Check `bootstrap.log` in the plugin-data directory if the
MCP server does not connect.

Claude Code uses the macOS Keychain where supported. On platforms without a
supported keychain, sensitive plugin configuration may be stored in
`~/.claude/.credentials.json`; protect that file with user-only permissions.

The same installation can be started from a regular shell:

```powershell
claude plugin marketplace add LilianaZhu/regulation-to-markdown
claude plugin install regulation-to-markdown@liliana-legal-tools --scope user
```

Do not pass the Token with `--config` on a shared machine because that would put
it in shell history. Use the interactive configuration dialog.

For local development:

```powershell
claude --plugin-dir C:\path\to\regulation-to-markdown
```

Or:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Dev -InstallClaudePlugin
```

## Other Agent Plugin clients

Clients implementing Agent Plugins 1.0.0 can load the root `plugin.json` and
`mcp.json`. Because the portable standard does not define credential storage,
set `MINERU_API_TOKEN` in the host environment before enabling MCP.

The MCP runtime is installed into the client's persistent plugin data directory,
not into the plugin source tree.

## Use

Claude Code does not need a chat attachment. Give the skill an accessible local
PDF path (placing the PDF in the current workspace minimizes permission prompts):

```text
/regulation-to-markdown:regulation-to-markdown "C:\path\to\official-regulation.pdf"
```

Workflow:

1. inspect source PDF and propose Reliable/Economical split plans;
2. require explicit user confirmation before MinerU upload;
3. preserve MinerU raw output and deterministically normalize Markdown;
4. merge only after overlap hashes match;
5. audit the merged Markdown against PDF text and rendered pages;
6. apply only approved, source-verified repairs;
7. independently verify the final file;
8. pass release gates and export only `FINAL.md` plus
   `validation-report.md`.

The implementation does not assume Indonesian BAB/Pasal structure. The agent
detects the source document's own hierarchy.

## Safety guarantees

- MinerU output is evidence, not authority.
- Python formatting may not change the visible text stream.
- Audit does not edit Markdown.
- Legal wording changes require a PDF page, exact source quote, approval, repair
  log, and independent verification.
- Official-source anomalies remain verbatim and are documented.
- Broken images, incomplete audits, unresolved high findings, hash mismatches,
  or unreviewed meaningful visuals block release.
- Job directories are ignored by Git and remain local.

## Runtime files

Each document gets an isolated job directory:

```text
jobs/<document-id>/
├── job.json
├── events.jsonl
├── batches/
├── merged/
├── audit/
├── final/
└── validation-report.md
```

Only the final Markdown and validation report are exportable release artifacts.

## Development

```powershell
python -m pip install --upgrade ".[dev]"
python -m pytest
python -m ruff check .
python -m ruff format --check .
claude plugin validate .
```

## Distribution

The repository contains a Claude marketplace catalog at:

```text
.claude-plugin/marketplace.json
```

Users can add the GitHub or GitLab repository directly as a marketplace. Claude
Code supports git marketplace sources and copies installed versions into its
managed cache.

## Project layout

```text
plugin.json                         Agent Plugins manifest
mcp.json                            Agent Plugins MCP definition
.claude-plugin/plugin.json          Claude Code/Desktop manifest
.claude-plugin/marketplace.json     Claude marketplace catalog
.mcp.json                           Claude MCP configuration
skills/regulation-to-markdown/      Agent workflow and review rules
scripts/mcp_launcher.py             Persistent isolated Python runtime launcher
src/regulation_to_markdown/         Deterministic implementation
tests/                              Unit, security, and integration tests
```

## References

- <https://agent-plugins.org/plugin-authors/manifest>
- <https://agent-plugins.org/plugin-authors/mcp-servers>
- <https://code.claude.com/docs/en/plugins>
- <https://code.claude.com/docs/en/discover-plugins>
- <https://mineru.net/apiManage/docs>
