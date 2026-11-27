"""Minimal MCP stdio adapter for a private Linux synthetic lab, not a production server."""
import argparse
import json
import os
from pathlib import Path
import stat
import sys
import time

from framework.spec import parse
from shadow_runtime.store import ShadowMarkdownStore

PROTOCOL = "2024-11-05"
MAX_LINE = 262144
TOOL = "shadow_request"


def lab_root(path):
    # The trusted launcher owns this directory; remote tool arguments cannot choose it.
    root = Path(path)
    parent = Path("/tmp").resolve()
    if (not root.is_absolute() or root.resolve() != root or root.parent != parent
            or not root.name.startswith("lingshu-mcp-") or not root.is_dir()):
        raise ValueError("private lab root required")
    info = root.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("private lab root required")
    return root


class Session:
    def __init__(self, store, principal):
        self.store = store
        self.principal = principal
        self.phase = "new"

    def dispatch(self, message):
        if type(message) is not dict or message.get("jsonrpc") != "2.0" or type(message.get("method")) is not str:
            return error(None, -32600)
        method = message["method"]
        if "id" not in message:
            if method == "notifications/initialized" and self.phase == "initializing":
                self.phase = "ready"
            return None  # notifications cannot cause store calls
        ident = message["id"]
        if type(ident) not in (int, str):
            return error(None, -32600)
        params = message.get("params", {})
        if type(params) is not dict:
            return error(ident, -32602)
        result = None
        if method == "initialize" and self.phase == "new" and type(params.get("protocolVersion")) is str:
            self.phase = "initializing"
            result = dict(protocolVersion=PROTOCOL, capabilities={"tools": {}},
                          serverInfo=dict(name="lingshu-isolated-shadow", version="0.1"))
        elif method == "ping":
            result = {}
        elif self.phase != "ready":
            return error(ident, -32600)
        elif method == "tools/list" and not params:
            result = dict(tools=[dict(name=TOOL, description="Submit a v2 request to the disposable synthetic store.",
                                      inputSchema=dict(type="object", properties={"request": {"type": "object"}},
                                                       required=["request"], additionalProperties=False))])
        elif method == "tools/call":
            if (set(params) != {"name", "arguments"} or params["name"] != TOOL
                    or type(params["arguments"]) is not dict or set(params["arguments"]) != {"request"}
                    or type(params["arguments"]["request"]) is not dict):
                return error(ident, -32602)
            req = params["arguments"]["request"]
            # Deliberately expose only this experiment's operations and process durability.
            kind = req.get("kind")
            if kind not in ("Read.get", "Read.receipt", "Write.create") or (
                    kind == "Write.create" and (self.principal != "alice" or req.get("durability_request") != "process")):
                result = dict(isError=True, content=[dict(type="text", text="operation not available in this lab")])
            else:
                now = int(time.time())
                ctx = dict(tenant="fixture", principal=self.principal, clearance=2, auth_epoch=1,
                           policy_generation=1, expires_at=now+60)
                try:
                    value = self.store.execute(req, ctx, now)
                except (OSError, ValueError, TypeError, KeyError, RecursionError):
                    result = dict(isError=True, content=[dict(type="text", text="request rejected by lab backend")])
                else:
                    result = dict(content=[dict(type="text", text=json.dumps(value, ensure_ascii=True))])
        else:
            return error(ident, -32601)
        return dict(jsonrpc="2.0", id=ident, result=result)


def error(ident, code):
    return dict(jsonrpc="2.0", id=ident, error=dict(code=code, message={
        -32700:"Parse error", -32600:"Invalid request", -32601:"Method not found", -32602:"Invalid params"}[code]))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--synthetic", action="store_true", required=True)
    cli.add_argument("--lab-root", required=True)
    cli.add_argument("--principal", choices=("alice", "bob"), required=True)
    args = cli.parse_args()
    if sys.platform != "linux":
        cli.error("Linux lab only")
    try:
        root = lab_root(args.lab_root)
    except ValueError as exc:
        cli.error(str(exc))
    session = Session(ShadowMarkdownStore(root, synthetic=True), args.principal)
    while raw := sys.stdin.buffer.readline(MAX_LINE+1):
        if len(raw) > MAX_LINE:
            return 2  # terminate; do not treat the remaining bytes as a fresh frame
        try:
            item = parse(raw.decode("utf-8", errors="strict"))
        except (ValueError, RecursionError):
            response = error(None, -32700)
        else:
            response = session.dispatch(item)
        if response is not None:
            print(json.dumps(response, ensure_ascii=True, allow_nan=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
