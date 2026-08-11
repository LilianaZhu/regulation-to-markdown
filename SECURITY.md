# Security

## Supported version

Security fixes are applied to the latest release on the `main` branch.

## Sensitive material

- Never commit MinerU tokens, `.env` files, official PDFs, split PDFs, signed
  download URLs, MinerU ZIPs, findings, repair evidence, or job state.
- Configure `MINERU_API_TOKEN` through Cursor plugin variables.
- Keep each document's `work/` directory local and access-controlled.
- Review the repository before approving installation or MCP execution.

The local MCP can read the selected source PDF and can write only within the
document work directory for conversion outputs. It sends confirmed PDF batches
to the official MinerU Precision API.

## Reporting a vulnerability

Open a private GitHub security advisory in this repository. Do not include real
tokens, signed URLs, private regulations, or other confidential source material
in the report.
