# Changelog

All notable changes to this project are documented here.

## 0.2.2 - 2026-08-14

- Prevent MinerU credential variables from reaching venv, pip, or Python build
  subprocesses during first-run bootstrap.
- Avoid creating an unused standalone runtime before local Marketplace installs.
- Document the automatic first-run runtime and platform-specific credential
  storage behavior.

## 0.2.1 - 2026-08-14

- Make the GitHub marketplace installation path explicit for Claude Code CLI.
- Improve the built-in secure MinerU Token configuration prompt.
- Repair CI manifest validation after removal of the legacy Cursor manifest.

## 0.2.0 - 2026-08-13

- Migrate the package from Cursor-specific Plugin metadata to the portable Agent
  Plugins 1.0.0 manifest and MCP schema.
- Add Claude Code/Desktop manifests, secure MinerU Token user configuration, and
  a GitHub/GitLab-compatible Claude marketplace catalog.
- Add an isolated persistent Python runtime launcher under plugin data.
- Add meaningful-image review gates, repair-log reconciliation, concise
  schema-v2 validation reports, and release-approved artifact export.
- Ignore local job evidence and remove the duplicate command entry.

## 0.1.0 - 2026-08-11

- Add the Cursor Plugin manifest, Skill, command, and local stdio MCP server.
- Add deterministic PDF splitting, MinerU extraction, normalization, overlap-safe
  merging, source-verified repair, independent review tracking, and release
  validation.
- Enforce job-state transitions, work-directory boundaries, unique MinerU result
  matching, signed-URL redaction, and download/ZIP resource limits.
- Add Windows installation, GitHub-assisted installation guidance, CI, and tests.
