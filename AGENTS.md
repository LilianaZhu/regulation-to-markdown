# Instructions for coding agents

If a user asked you to install this plugin, follow this file exactly. Do not
improvise an MCP configuration by hand, and do not tell the user to set a
system environment variable.

## Install

Clone the repository somewhere permanent, because the MCP entry points at the
clone directory:

```bash
git clone https://github.com/LilianaZhu/regulation-to-markdown.git
cd regulation-to-markdown
python scripts/setup.py
```

`scripts/setup.py` uses only the standard library and needs Python 3.12 or
newer. It builds an isolated runtime, stores the MinerU token, and registers
the MCP server in every coding agent it detects.

## Handling the MinerU token

The script prompts for the token with a hidden input. Prefer that path.

**Never ask the user to paste the token into the chat, and never pass it with
`--token` on a shared machine, because both leave the secret in a transcript or
in shell history.** If you are running the command for the user in a
non-interactive shell, tell them to run `python scripts/setup.py` themselves in
a terminal so the hidden prompt works.

Direct the user to https://mineru.net/apiManage/token to create a token.

The token is written to `~/.regulation-to-markdown/credentials.json` with
owner-only permissions. The server reads it from there, so it does **not**
depend on the host forwarding environment variables. This matters because
several hosts, Cursor among them, give stdio MCP servers a curated environment
and drop inherited variables.

## After setup

Tell the user to restart the agent, or to run `Developer: Reload Window` in
Cursor, so the new MCP server is picked up.

Verify by checking that the `regulation-to-markdown` MCP server is connected
and exposes `inspect_pdf_and_propose_splits`.

## Useful flags

| Command | Effect |
| --- | --- |
| `python scripts/setup.py --print-config` | Show the MCP entry, change nothing |
| `python scripts/setup.py --host cursor` | Register one host only |
| `python scripts/setup.py --host none` | Store the token, print the entry to add manually |
| `python scripts/setup.py --skip-runtime` | Re-register or rotate the token without rebuilding |

Rotating the token later is just `python scripts/setup.py --skip-runtime`.

## Troubleshooting

**"No MinerU API token is reachable"** — setup never ran, or it wrote to a
different data directory. Check that `~/.regulation-to-markdown/credentials.json`
exists, then confirm the `REG2MD_PLUGIN_DATA` value in the host's MCP entry
points at the directory that actually holds that file.

**The server fails to start** — read `bootstrap.log` in the plugin data
directory. Re-run `python scripts/setup.py` to rebuild the runtime.

**Two servers with the same name** — if the host also auto-loads this repo's
`mcp.json` or `.mcp.json` as a plugin, disable that copy and keep the entry
written by `setup.py`.

**Do not hand-edit the host config to add `${PLUGIN_ROOT}` or
`${user_config.mineru_api_token}`.** Cursor and several other hosts leave those
placeholders unexpanded, which is what makes hand-written configs fail.
