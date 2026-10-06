"""Verify stdio MCP handshake: initialize -> tools/list. Prints the tool list."""

import json
import subprocess
import sys

PY = r"C:\Users\archi\Desktop\Testing\Code\MCP\Issue_Function\.venv\Scripts\python.exe"
MAIN = r"C:\Users\archi\Desktop\Testing\Code\MCP\Issue_Function\main.py"

REQUESTS = [
    {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "probe", "version": "1"},
        },
    },
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
]

payload = "".join(json.dumps(r) + "\n" for r in REQUESTS)

proc = subprocess.run(
    [PY, MAIN], input=payload, capture_output=True, text=True, timeout=60
)

for line in proc.stdout.splitlines():
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    if msg.get("id") == 2:
        for tool in msg["result"]["tools"]:
            schema = tool.get("inputSchema", {}).get("properties", {})
            print(f"TOOL {tool['name']}({', '.join(schema)}) -> {tool.get('description', '')}")
        break
else:
    print("NO tools/list RESPONSE")
    print("stdout:", proc.stdout[:2000])
    print("stderr:", proc.stderr[:2000])
    sys.exit(1)

print("HANDSHAKE OK")
