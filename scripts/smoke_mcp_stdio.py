#!/usr/bin/env python3
"""
scripts/smoke_mcp_stdio.py — end-to-end stdio handshake (PROJ-324..328)

Launches each MCP server as a real subprocess and performs an actual
initialize + tools/list exchange over stdio. Unlike test_mcp_servers.py,
which inspects the objects in-process, this proves the server starts, speaks
JSON-RPC, and does not corrupt stdout with log output.

Run: python scripts/smoke_mcp_stdio.py
"""

import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SERVERS = {
    "literature": "skills.mcp.literature_server",
    "amazon": "skills.mcp.amazon_server",
}

PASS = 0
FAIL = 0


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}{(' — ' + detail) if detail else ''}")


def send(proc, payload):
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()


def read_json(proc, timeout=25.0):
    """Read newline-delimited JSON-RPC responses until one parses."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            # Anything unparseable on stdout is itself the bug we are checking
            # for, so surface it rather than skipping quietly.
            return {"_unparseable": line[:200]}
    return None


def smoke(name, module) -> None:
    env = dict(os.environ, PYTHONPATH=ROOT, PYTHONUNBUFFERED="1")
    proc = subprocess.Popen(
        [sys.executable, "-m", module],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        bufsize=1,
    )

    try:
        send(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "smoke-test", "version": "1.0"},
            },
        })

        resp = read_json(proc)
        if resp is None:
            err = (proc.stderr.read() or "")[-600:]
            check(f"{name}: responds to initialize", False, f"no response. stderr: {err}")
            return
        if "_unparseable" in resp:
            check(f"{name}: stdout carries only JSON-RPC", False, resp["_unparseable"])
            return

        check(f"{name}: responds to initialize", "result" in resp, str(resp)[:200])
        info = resp.get("result", {}).get("serverInfo", {})
        check(f"{name}: reports serverInfo", bool(info.get("name")), str(info))

        send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

        resp = read_json(proc)
        tools = (resp or {}).get("result", {}).get("tools", [])
        check(f"{name}: tools/list returns 4 tools", len(tools) == 4, f"got {len(tools)}")

        named = all(t.get("name", "").startswith(name.split('_')[0][:4]) or t.get("name")
                    for t in tools)
        check(f"{name}: every tool has a name and schema",
              named and all(t.get("inputSchema") for t in tools),
              str([t.get("name") for t in tools]))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    print("MCP stdio smoke test (PROJ-324..328)\n")
    try:
        import mcp  # noqa: F401
    except ImportError:
        print("  SKIP  mcp SDK not installed")
        return 0

    for name, module in SERVERS.items():
        print(f"  --- {module}")
        smoke(name, module)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
