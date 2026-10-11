# issue-function — GitHub issue management over MCP

Five tools against the repo named by `GITHUB_REPO`: `create_issue`,
`list_open_issues`, `get_issue`, `close_issue`, `add_label`.

## Configuration

Copy the template and fill it in:

```bash
copy .env.example .env
```

```text
ACCESS_TOKEN=github_pat_xxx
GITHUB_REPO=owner/repo
```

`.env` is read from next to `main.py`, so the server works from any working
directory. A missing variable fails the call with a named error rather than a
stack trace.

## Install, test, verify

```bash
uv sync --extra dev
.venv\Scripts\python.exe -m pytest -q     # 34 tests
.venv\Scripts\python.exe verify_mcp.py    # real stdio handshake + contract
```

`verify_mcp.py` starts `main.py` as a subprocess, runs `initialize` and
`tools/list`, and asserts that all five tools are advertised with the four
annotations each. It exits non-zero on any mismatch.

## Register with pi (or any MCP host)

Add to your host's `mcp.json` (top-level key is `mcpServers`), with
`<repo>` set to this repository's checkout path:

```json
{
  "mcpServers": {
    "issue-function": {
      "command": "<repo>\\.venv\\Scripts\\python.exe",
      "args": ["<repo>\\main.py"]
    }
  }
}
```

Then run **`/reload`** in pi. Confirm with `mcp({})`: `issue-function (5 tools)`.

## Tools

Every tool returns `{"success": true, ...}` on success. Annotations are what the
host shows you before it calls something, so read them:

| Tool | readOnly | destructive | idempotent |
|---|---|---|---|
| `create_issue(issue_title, issue_text, labels?, assignees?)` | no | yes | no |
| `list_open_issues(limit=10, labels?, assignee?)` | yes | no | yes |
| `get_issue(issue_number)` | yes | no | yes |
| `close_issue(issue_number, state_reason="completed")` | no | yes | yes |
| `add_label(issue_number, label)` | no | yes | yes |

`state_reason` is `"completed"` or `"not_planned"`. `limit` is 1–100.
`add_label` creates the label on the repo if it does not exist there yet.

## Behaviour worth knowing

- **Pull requests are excluded** from `list_open_issues`. GitHub's issues
  endpoint returns them alongside issues; they are filtered out so the tool means
  what its name says.
- **No filter means no filter.** Omitting `labels`/`assignee` sends `None` to
  GitHub, not an empty list or empty string — those would ask GitHub for issues
  matching nothing.
- **Idempotency is real.** `close_issue` and `add_label` read the
  issue first and return the existing state instead of re-writing it.
- **Errors are typed.** Failures raise `MCPError`, which the SDK forwards as a
  JSON-RPC error: 4xx from GitHub becomes `INVALID_PARAMS` (-32602), 5xx becomes
  `INTERNAL_ERROR` (-32603). The HTTP status is preserved in `data.status`. Any
  other exception is reported as an `isError` result rather than crashing the
  server.

## Token permissions

Fine-grained PAT with **Issues** (read/write) and **Metadata** (always required),
scoped to `GITHUB_REPO`. See `.env.example`.

## License

MIT — see `LICENSE`.

[![M8ven Score](https://m8ven.ai/badge/mcp/engine-user-issue-function-mcp-hne13m?v=8016310ae21a52b17b682fdb51655c46)](https://m8ven.ai/mcp/engine-user-issue-function-mcp-hne13m?s=readme)
