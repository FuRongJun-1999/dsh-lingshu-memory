"""JSON stdin/stdout demo; explicit --synthetic, no paths, no network or host discovery."""
import argparse
import copy
import json
import sys
from framework.api import _json_domain
from framework.spec import parse
from sandbox_runtime.store import SyntheticStore, Probe
from sandbox_runtime.controller import Controller, AlertSink


def execute(value):
    _json_domain(value)
    if type(value) is not dict or set(value)!={"fixture","context","now","task"}:raise ValueError("INVALID_ENVELOPE")
    probe=Probe();alerts=AlertSink()
    store=SyntheticStore(value["fixture"],synthetic=True,probe=probe)
    c=Controller(store,probe,context_provider=lambda:copy.deepcopy(value["context"]),clock=lambda:value["now"],alerts=alerts)
    output=c.run(value["task"])
    return {"output":output,"actions":copy.deepcopy(probe.events),"alerts":copy.deepcopy(alerts.events)}


def main():
    parser=argparse.ArgumentParser(description="Synthetic context action-loop replay only")
    parser.add_argument("--synthetic",action="store_true",required=True)
    parser.parse_args()
    try:
        raw=sys.stdin.buffer.read(131073)
        if len(raw)>131072:raise ValueError("INPUT_LIMIT")
        value=parse(raw.decode("utf-8",errors="strict"))
        result=execute(value)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True,allow_nan=False))
        return 0 if result["output"]["status"]=="ready" else 3
    except Exception:
        print(json.dumps({"output":{"status":"blocked","reason":"INVALID_INPUT"}},sort_keys=True))
        return 2


if __name__=="__main__":raise SystemExit(main())
