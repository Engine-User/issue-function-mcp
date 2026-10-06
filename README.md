# issue-function — MCP server that creates GitHub issues

One tool: `create_issue(issue_title, issue_text)`. Creates an issue in the repo named
by `GITHUB_REPO` and returns its URL.

## Configuration

`.env` next to `main.py`:

```text
ACCESS_TOKEN=github_pat_xxx
GITHUB_REPO=owner/repo
```

Install and verify:

```bash
uv sync
.venv\Scripts\python.exe verify_mcp.py     # handshake + prints the tool list
```

## Register with pi (or any MCP host)

Add to `C:\Users\archi\.config\mcp\mcp.json` (top-level key is `mcpServers`):

```json
{
  "mcpServers": {
    "issue-function": {
      "command": "C:\\Users\\archi\\Desktop\\Testing\\Code\\MCP\\Issue_Function\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\archi\\Desktop\\Testing\\Code\\MCP\\Issue_Function\\main.py"
      ]
    }
  }
}
```

Then run **`/reload`** in pi. Confirm with `mcp({})`: `issue-function (1 tool)`.

## Use

In pi the tool appears as `issue-function_create_issue`, or call it through the gateway:

```js
mcp({ server: "issue-function" })                                  // list tools
mcp({ tool: "issue-function_create_issue",
     args: { issue_title: "Bug: login fails", issue_text: "Steps to reproduce…" } })
```

## Token permissions

Fine-grained PAT with **Issues** (read/write) and **Metadata** (always required),
scoped to `GITHUB_REPO`.

**Note:** the server only *creates* issues. It cannot close or delete them. Adding cleanup as a repeatable tool requires a second `@mcp.tool()`. This is just an example of a working MCP server, not a full-featured GitHub client.