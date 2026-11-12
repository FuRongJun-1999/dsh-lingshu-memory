"""Migration planning only; no conversion, authorization or old-code execution."""
import base64
import copy
import datetime as dt
import hashlib
import re
from framework.api import _json_domain
from framework.spec import ROOT, canonical, parse

CG_OPS = frozenset("route read write verify review protect identity consistency metacognition self_state evolution sustain scrub predict causal forget goal task recent state_view state_event info index_code index_doc ref whitebox theory link session ingest export maintain consolidate insight ccg status edges audit help".split())
STG_OPS = frozenset("relation timeline anchors consistency state_chain".split())


def load_inventory():
    value=parse((ROOT/"spec/compatibility.json").read_text(encoding="utf-8"))
    if value["upstream_commit"]!="b450d2f451ed33891e3f6587d238d1d4f5c9ecb9" or value["source_sha256"]!="071eb877ba3a2bcb43fd01a8e9a367a9b3b3e69b26d3b4736f4e902a3aceeaba": raise ValueError("SOURCE_DRIFT")
    rows=value["operations"]
    expected={("cg",x) for x in CG_OPS}|{("stg",x) for x in STG_OPS}
    if value["default"] != "reject" or len(rows) != len(expected): raise ValueError("INVENTORY_DRIFT")
    seen=set()
    for row in rows:
        key=(row["tool"],row["op"])
        if key not in expected or key in seen or row["runtime_ready"] is not False: raise ValueError("INVENTORY_DRIFT")
        target={"read":"Read","route":"Read","status":"Read","edges":"Read","write":"Write","forget":"Govern"}.get(row["op"],"extension") if row["tool"]=="cg" else "extension"
        if row["target"] != target: raise ValueError("INVENTORY_DRIFT")
        if type(row["source_line"]) is not int or row["source_line"] < 1: raise ValueError("INVENTORY_DRIFT")
        seen.add(key)
    return value


def operation_plan(tool, op):
    if type(tool) is not str or type(op) is not str: raise ValueError("INVALID_ARGUMENT")
    row=next((x for x in load_inventory()["operations"] if x["tool"]==tool and x["op"]==op),None)
    if row is None: return {"decision":"reject","target":None,"runtime_ready":False}
    return {"decision":"specification_only","target":row["target"],"runtime_ready":False}


def downgrade(read_required, write_required, available):
    # read_required includes ALL security/conditions/time/source guarantees of reads.
    if any(type(x) is not list or not x or any(type(v) is not str or not v for v in x) or len(x)!=len(set(x)) for x in (read_required,write_required)):
        raise ValueError("INVALID_ARGUMENT")
    if type(available) is not dict or any(type(k) is not str or not k or (v is not None and type(v) is not bool) for k,v in available.items()): raise ValueError("INVALID_ARGUMENT")
    if any(available.get(x) is False for x in read_required): return "reject"
    if any(available.get(x) is not True for x in read_required): return "defer"
    if any(available.get(x) is False for x in write_required): return "read_only"
    if any(available.get(x) is not True for x in write_required): return "defer"
    return "eligible_isolated_shadow"


def legacy_capsule(raw):
    if type(raw) is not bytes or len(raw)>131072: raise ValueError("INVALID_ARGUMENT")
    try: raw.decode("utf-8",errors="strict"); encoding="utf8"
    except UnicodeError: encoding="opaque_bytes"
    return {"encoding":encoding,"raw_base64":base64.b64encode(raw).decode("ascii"),"sha256":hashlib.sha256(raw).hexdigest(),"interpretation":"DEFER"}


def restore_capsule(value):
    if type(value) is not dict or set(value)!={"encoding","raw_base64","sha256","interpretation"}: raise ValueError("INVALID_ARGUMENT")
    if type(value["raw_base64"]) is not str or len(value["raw_base64"])>174764: raise ValueError("INVALID_ARGUMENT")
    try: raw=base64.b64decode(value["raw_base64"],validate=True)
    except Exception as ex: raise ValueError("INVALID_ARGUMENT") from ex
    if legacy_capsule(raw)!=value: raise ValueError("CAPSULE_MISMATCH")
    return raw


def instant(value):
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",value) is None: raise ValueError("INVALID_TIME")
    try: return dt.datetime.strptime(value,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError as ex: raise ValueError("INVALID_TIME") from ex


def bound(value):
    if type(value) is not dict or type(value.get("state")) is not str: raise ValueError("INVALID_BOUND")
    state=value["state"]
    if state in ("unknown","unbounded"):
        if set(value)!={"state"}: raise ValueError("INVALID_BOUND")
        return state,None
    if state=="instant" and set(value)=={"state","value"}: return state,instant(value["value"])
    raise ValueError("INVALID_BOUND")


def interval(value):
    if type(value) is not dict or set(value)!={"start","end"}: raise ValueError("INVALID_INTERVAL")
    a,b=bound(value["start"]),bound(value["end"])
    if a[0]==b[0]=="instant" and a[1]>b[1]: raise ValueError("REVERSED_INTERVAL")
    return a,b


def time_bundle(value):
    _json_domain(value)
    if type(value) is not dict or set(value)!={"observed","effective"}: raise ValueError("AXIS_REQUIRED")
    for x in value.values(): interval(x)
    return copy.deepcopy(value)


def time_match(value, axis, point):
    if type(axis) is not str or axis not in ("observed","effective"): raise ValueError("AXIS_REQUIRED")
    time_bundle(value);p=instant(point);a,b=interval(value[axis])
    # A known contradiction decides even if the other bound is unknown.
    if a[0]=="instant" and p<a[1]: return "NO_MATCH"
    if b[0]=="instant" and p>=b[1]: return "NO_MATCH"
    if a[0]=="unknown" or b[0]=="unknown": return "DEFER"
    return "MATCH"


def condition_bundle(value):
    _json_domain(value)
    if type(value) is not dict or set(value)!={"carrier","method","existence"}: raise ValueError("CONDITION_REQUIRED")
    for item in value.values():
        if type(item) is not dict: raise ValueError("INVALID_CONDITION")
        if item=={"state":"unknown"}: continue
        if set(item)!={"state","text"} or item["state"]!="declared" or type(item["text"]) is not str or not 1<=len(item["text"])<=4096: raise ValueError("INVALID_CONDITION")
    if len(canonical(value))>131072: raise ValueError("INVALID_CONDITION")
    return copy.deepcopy(value)
