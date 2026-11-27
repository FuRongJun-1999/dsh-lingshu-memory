"""Independent wire client. Runs real child servers, not in-process mocks."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
from linux_process_kill import fixture

ROOT = Path(__file__).resolve().parents[1]


def check(condition, reason):
    if not condition:
        raise AssertionError(reason)


@contextmanager
def connect(root, principal):
    argv = [sys.executable, "-X", "utf8", "-B", "-m", "shadow_runtime.mcp_lab",
            "--synthetic", "--lab-root", str(root), "--principal", principal]
    with subprocess.Popen(argv, cwd=ROOT, shell=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="strict") as proc:
        ident = 0
        def send(method, params=None, note=False):
            nonlocal ident
            message = dict(jsonrpc="2.0", method=method)
            if params is not None:
                message["params"] = params
            if not note:
                ident += 1
                message["id"] = ident
            proc.stdin.write(json.dumps(message)+"\n")
            proc.stdin.flush()
            if note:
                return None
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                check(selector.select(10), "MCP timeout")
                reply = json.loads(proc.stdout.readline())
            check(reply["jsonrpc"] == "2.0" and reply["id"] == ident, "wrong reply correlation")
            return reply
        try:
            init = send("initialize", dict(protocolVersion="2024-11-05", capabilities={}, clientInfo=dict(name="wire-lab",version="1")))
            check(init["result"]["protocolVersion"] == "2024-11-05", "wrong protocol")
            check(send("tools/list")["error"]["code"] == -32600, "missing initialization gate")
            send("notifications/initialized", note=True)
            tools = send("tools/list")["result"]["tools"]
            check([t["name"] for t in tools] == ["shadow_request"], "wrong tool surface")
            yield proc.pid, send
        finally:
            if proc.stdin:
                proc.stdin.close()
                proc.stdin = None
            try:
                rest, err = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate(timeout=5)
                raise
            check(proc.returncode == 0 and not rest.strip() and not err.strip(), "unclean MCP exit")


def call(send, req):
    result = send("tools/call", dict(name="shadow_request", arguments=dict(request=req)))["result"]
    check(not result.get("isError"), "unexpected tool refusal")
    return json.loads(result["content"][0]["text"])


def main():
    request, _, read = fixture()
    search = {k:v for k,v in read.items() if k != "node_id"}
    search.update(kind="Read.search",query="blue",limit=1)
    with tempfile.TemporaryDirectory(prefix="lingshu-mcp-", dir="/tmp") as tmp:
        with connect(tmp,"alice") as (a,send):
            created = call(send,request)
            check(created["outcome"]=="ok", "write failed")
            original=created["historical_receipt"]
            check(original["commit_status"]=="committed", "missing commit")
        with connect(tmp,"bob") as (b,send):
            denied=call(send,read)
            check(denied["error_code"]=="NOT_FOUND_OR_DENIED" and denied["records"] is None,"foreign read")
            check(call(send,search)["records"]==[],"foreign search disclosed record")
            injected=send("tools/call",dict(name="shadow_request",arguments=dict(request=read,context=dict(principal="alice"))))
            check(injected["error"]["code"]==-32602,"request can override launch identity")
            blocked=send("tools/call",dict(name="shadow_request",arguments=dict(request=request)))
            check(blocked["result"]["isError"] is True,"read-only session can write")
        with connect(tmp,"alice") as (c,send):
            restored=call(send,read)["records"]
            check(len(restored)==1 and restored[0]["body"]==request["content"] and restored[0]["locator"]==
                  dict(id=original["node_id"],revision=1,content_sha=hashlib.sha256(request["content"].encode()).hexdigest()), "read mismatch")
            check(call(send,search)["records"]==restored,"authorized search differs from known read")
            check(call(send,dict(search,query="absentphrase"))["records"]==[],"unmatched query returned records")
            check(call(send,request)["historical_receipt"]==original,"replay changed historical receipt")
            check(call(send,dict(request,content="changed fixture"))["error_code"]=="TOKEN_PAYLOAD_CONFLICT","token conflict accepted")
        rows=[json.loads(line) for line in (Path(tmp)/"audit/audit.jsonl").read_text(encoding="utf-8").splitlines()]
        check(len({a,b,c})==3,"servers are not distinct")
        check(len(rows)==1 and rows[0]["writer_id"]==original["writer_id"] and rows[0]["payload_sha"]==original["content_sha"],"audit disagreement")
        print(json.dumps(dict(schema=1,protocol="2024-11-05",server_pids=[a,b,c],audit_rows=len(rows),
                              receipt_replay="PASS",authorized_read="PASS",foreign_read="DENIED",identity_override="REJECTED",
                              search_contrast="PASS",dsh_bridge="NOT_RUN",production="NOT_RUN"),sort_keys=True))


if __name__ == "__main__":
    main()
