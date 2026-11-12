"""Explicit synthetic normalized-event replay through stdin. No host installation."""
import copy
import json
import sys
import argparse
from framework.api import _json_domain
from framework.spec import parse
from framework.security import context_shape
from sandbox_runtime.store import SyntheticStore, Probe
from sandbox_runtime.controller import Controller, AlertSink, task_shape
from sandbox_runtime.replay import Replay


def execute(value):
    _json_domain(value)
    if type(value) is not dict or set(value)!={"fixture","context","now","bootstrap_task","stream","session","events"}:raise ValueError("INVALID_ENVELOPE")
    context_shape(value["context"]);task_shape(value["bootstrap_task"])
    if type(value["now"]) is not int or not 0<=value["now"]<=9007199254740991:raise ValueError("INVALID_NOW")
    if type(value["events"]) is not list or len(value["events"])>256:raise ValueError("EVENT_LIMIT")
    probe=Probe();alerts=AlertSink();store=SyntheticStore(value["fixture"],synthetic=True,probe=probe)
    controller=Controller(store,probe,context_provider=lambda:copy.deepcopy(value["context"]),clock=lambda:value["now"],alerts=alerts)
    adapter=Replay(controller,stream=value["stream"],session=value["session"],bootstrap_task=value["bootstrap_task"])
    results=[adapter.handle(event) for event in value["events"]]
    # Deliberate test transcript, not an exactly-once delivery API.
    return {"results":results,"spent":copy.deepcopy(adapter.spent),"receipts":copy.deepcopy(adapter.receipts),"actions":copy.deepcopy(probe.events),"alerts":copy.deepcopy(alerts.events)}


def main():
    p=argparse.ArgumentParser();p.add_argument("--synthetic",action="store_true",required=True);p.parse_args()
    try:
        raw=sys.stdin.buffer.read(262145)
        if len(raw)>262144:raise ValueError("INPUT_LIMIT")
        result=execute(parse(raw.decode("utf-8",errors="strict")))
        print(json.dumps(result,ensure_ascii=True,sort_keys=True,allow_nan=False))
        return 3 if any(x["status"]=="blocked" for x in result["results"]) else 0
    except Exception:
        print(json.dumps({"status":"blocked","reason":"INVALID_INPUT"},sort_keys=True));return 2


if __name__=="__main__":raise SystemExit(main())
