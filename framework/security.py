"""Trusted evidence predicates only. No authentication, deletion or atomic emission."""
import copy
import re
from framework.api import _json_domain

MAX=9007199254740991
CONTEXT={"tenant","principal","clearance","auth_epoch","policy_generation","expires_at"}
SNAPSHOT={"id","content_generation","policy_generation","expires_at"}

def integer(v):
    return type(v) is int and 0<=v<=MAX

def context_shape(value):
    _json_domain(value)
    if type(value) is not dict or set(value)!=CONTEXT: raise ValueError("INVALID_CONTEXT")
    if any(type(value[k]) is not str or not 1<=len(value[k])<=128 for k in ("tenant","principal")): raise ValueError("INVALID_CONTEXT")
    if not integer(value["clearance"]) or value["clearance"]>3: raise ValueError("INVALID_CONTEXT")
    if any(not integer(value[k]) for k in ("auth_epoch","policy_generation","expires_at")): raise ValueError("INVALID_CONTEXT")
    return copy.deepcopy(value)

def binding_shape(value):
    _json_domain(value)
    if type(value) is not dict or set(value)!={"context","snapshot","read_kind","query_sha","response_sha","cursor_sha"}: raise ValueError("INVALID_BINDING")
    c=context_shape(value["context"]);s=value["snapshot"]
    if type(s) is not dict or set(s)!=SNAPSHOT: raise ValueError("INVALID_SNAPSHOT")
    if type(s["id"]) is not str or not 1<=len(s["id"])<=128 or any(not integer(s[k]) for k in ("content_generation","policy_generation","expires_at")): raise ValueError("INVALID_SNAPSHOT")
    if s["policy_generation"]!=c["policy_generation"]: raise ValueError("POLICY_MISMATCH")
    if type(value["read_kind"]) is not str or value["read_kind"] not in ("Read.get","Read.search","Read.expand","Read.receipt"): raise ValueError("INVALID_BINDING")
    for key in ("query_sha","response_sha","cursor_sha"):
        v=value[key]
        if key=="cursor_sha" and v is None: continue
        if type(v) is not str or re.fullmatch("[0-9a-f]{64}",v) is None: raise ValueError("INVALID_BINDING")
    if value["cursor_sha"] is not None and value["read_kind"] not in ("Read.search","Read.expand"): raise ValueError("INVALID_BINDING")
    return copy.deepcopy(value)

def emit_allowed(prepared, current, now, authenticated, allowed, cursor_validated):
    """current must describe the actual immutable prepared bytes/page, not a re-stamp."""
    if any(type(x) is not bool for x in (authenticated,allowed,cursor_validated)) or not integer(now): return False
    if not authenticated or not allowed or not cursor_validated: return False
    try: a,b=binding_shape(prepared),binding_shape(current)
    except (ValueError,TypeError,RecursionError): return False
    if a!=b: return False
    return now<a["context"]["expires_at"] and now<a["snapshot"]["expires_at"]

KINDS={"body","backup","index","audit","token_final","intent"}
STATES={"active","tombstoned","superseded","quarantined"}
FIELDS={"kind","lifecycle","deadline","authorized","legal_hold","commit_resolved","terminal_durable","dependencies_closed","audit_closed"}

def retention_plan(evidence, now):
    """Eligibility, never deletion. Tri-state evidence: missing knowledge retains."""
    if type(evidence) is not dict or set(evidence)!=FIELDS or not integer(now): raise ValueError("INVALID_RETENTION")
    e=evidence
    if type(e["kind"]) is not str or e["kind"] not in KINDS or type(e["lifecycle"]) is not str or e["lifecycle"] not in STATES: raise ValueError("INVALID_RETENTION")
    if e["deadline"] is not None and not integer(e["deadline"]): raise ValueError("INVALID_RETENTION")
    for k in FIELDS-{"kind","lifecycle","deadline"}:
        if e[k] is not None and type(e[k]) is not bool: raise ValueError("INVALID_RETENTION")
    if e["authorized"] is not True or e["legal_hold"] is not False: return "retain"
    if e["kind"]=="token_final": return "retain"
    if e["kind"]=="index": return "eligible_rebuild_discard"
    if e["deadline"] is None or now<e["deadline"]: return "retain"
    if e["lifecycle"] in ("active","quarantined"): return "retain"
    if any(e[k] is not True for k in ("commit_resolved","terminal_durable","dependencies_closed")): return "retain"
    if e["kind"]=="audit" and e["audit_closed"] is not True: return "retain"
    return "eligible_purge"
