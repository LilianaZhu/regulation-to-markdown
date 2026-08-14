# Security

## Supported version

Security fixes are applied to the latest release on the `main` branch.

## Sensitive material

- Never commit MinerU tokens, `.env` files, official PDFs, split PDFs, signed
  download URLs, MinerU ZIPs, findings, repair evidence, or job state.
- In Claude Code, configure the sensitive `mineru_api_token` plugin option. In
  other Agent Plugin clients, set `MINERU_API_TOKEN` in the host environment.
- The launcher removes MinerU credential variables before creating the virtual
  environment or invoking pip/build subprocesses, then restores them only for
  the final MCP server process.
- Claude Code may store sensitive configuration in `~/.claude/.credentials.json`
  on platforms without a supported system keychain. Protect that file with
  user-only permissions.
- Keep each document's `jobs/` or `work/` directory local and access-controlled.
- Review the repository before approving installation or MCP execution.

The local MCP can read the selected source PDF and can write only within the
document work directory for conversion outputs. It sends confirmed PDF batches
to the official MinerU Precision API.

## Reporting a vulnerability

Open a private GitHub security advisory in this repository. Do not include real
tokens, signed URLs, private regulations, or other confidential source material
in the report.
