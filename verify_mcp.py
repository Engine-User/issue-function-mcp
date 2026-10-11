"""Verify the stdio MCP handshake and the published tool contract.

Drives main.py as a real subprocess over stdio, then asserts on what
tools/list actually returns. Reading main.py's source text would be cheaper and
would also pass on a server that never starts.

Run:  .venv\\Scripts\\python.exe verify_mcp.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
PYTHON = BASE / ".venv" / "Scripts" / "python.exe"
SERVER = BASE / "main.py"

EXPECTED = {
    "create_issue": (False, True, False),
    "list_open_issues": (True, False, True),
    "get_issue": (True, False, True),
    "close_issue": (False, True, True),
    "add_label": (False, True, True),
}

REQUESTS = [
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "probe", "version": "1"},
        },
    },
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
]


def handshake() -> list[dict]:
    """Run the server and return its advertised tools."""
    payload = "".join(json.dumps(r) + "\n" for r in REQUESTS)
    proc = subprocess.run(
        [str(PYTHON), str(SERVER)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=BASE,
    )

    for line in proc.stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == 2:
            return msg["result"]["tools"]

    print("NO tools/list RESPONSE")
    print("stdout:", proc.stdout[:2000])
    print("stderr:", proc.stderr[:2000])
    sys.exit(1)


def main() -> int:
    print("=" * 60)
    print("issue-function - MCP handshake")
    print("=" * 60)

    if not PYTHON.exists():
        print(f"MISSING interpreter {PYTHON}. Run: uv sync --extra dev")
        return 1

    tools = handshake()
    by_name = {t["name"]: t for t in tools}
    failures: list[str] = []

    for name, (read_only, destructive, idempotent) in EXPECTED.items():
        tool = by_name.get(name)
        if tool is None:
            failures.append(f"{name}: not advertised")
            continue

        ann = tool.get("annotations") or {}
        props = tool.get("inputSchema", {}).get("properties", {})
        for key, want in (
            ("readOnlyHint", read_only),
            ("destructiveHint", destructive),
            ("idempotentHint", idempotent),
            ("openWorldHint", True),
        ):
            if ann.get(key) is not want:
                failures.append(f"{name}: {key}={ann.get(key)!r}, want {want!r}")
        if not ann.get("title"):
            failures.append(f"{name}: annotations.title missing")
        if not tool.get("description"):
            failures.append(f"{name}: description missing")

        summary = " ".join(tool.get("description", "").split())
        print(f"OK {name}({', '.join(props)}) -> {summary[:70]}")

    for extra in set(by_name) - set(EXPECTED):
        print(f"NOTE unexpected extra tool advertised: {extra}")

    print()
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print("  -", f)
        return 1

    print(f"HANDSHAKE OK - {len(EXPECTED)} tools, all annotations correct")
    return 0


if __name__ == "__main__":
    sys.exit(main())