"""Pure cancellation/response specification. No authentication, CAS or I/O."""
from framework.api import _json_domain, _validate, check_schema
from framework.spec import ROOT, parse
import copy

BASES = ("unassessed", "fresh_unseen", "preaccept_rejected", "durable_cancel")

def bools(*xs):
    if any(type(x) is not bool for x in xs): raise ValueError("INVALID_ARGUMENT")

def absence_basis(complete, matching, rejected, cancelled, fresh):
    bools(complete, matching, rejected, cancelled, fresh)
    if not complete or not matching or sum((rejected, cancelled, fresh)) != 1: return "unassessed"
    if rejected: return "preaccept_rejected"
    if cancelled: return "durable_cancel"
    return "fresh_unseen"

def cancellation(state, complete, matching, authorized, sealed_cancel, conflict=False):
    bools(complete, matching, authorized, sealed_cancel, conflict)
    if not authorized: return (None, None, "authenticate")
    if type(state) is not str or state not in ("unseen", "pending", "committed", "cancelled", "rejected", "unknown"): raise ValueError("INVALID_ARGUMENT")
    if conflict or not complete or not matching or state == "unknown": return ("unknown", "unknown", "query_same_token")
    if state in ("committed", "rejected"):
        if sealed_cancel: return ("unknown", "unknown", "query_same_token")
        return ("committed", "committed", "return_original") if state == "committed" else ("absent", "rejected", "return_original_rejection")
    if sealed_cancel: return ("absent", "cancelled", "return_original_cancel")
    return ("unknown", "unknown", "query_same_token")

def envelope(rid, scope, outcome, code, action, target):
    return validate_envelope(dict(version="0.2", request_id=rid, scope=scope, outcome=outcome, error_code=code, next_action=action, target=target))

def read_response(rid, allowed, succeeded):
    bools(allowed, succeeded)
    if not allowed: return envelope(rid,"read","error","NOT_FOUND_OR_DENIED","authenticate",None)
    if not succeeded: return envelope(rid,"read","error","READ_FAILED","retry_read",None)
    return envelope(rid,"read","ok",None,"none",None)

def target_response(rid, scope, status, audit, projection, receipt_allowed, content_allowed, negative="unassessed", conflict=False):
    bools(receipt_allowed, content_allowed, conflict)
    if type(scope) is not str or scope not in ("mutation","receipt"): raise ValueError("INVALID_ARGUMENT")
    if not receipt_allowed: return envelope(rid,scope,"error","NOT_FOUND_OR_DENIED","authenticate",None)
    if type(status) is not str or status not in ("committed","absent","unknown"): raise ValueError("INVALID_ARGUMENT")
    if type(audit) is not str or audit not in ("ok","missing","failed","unknown"): raise ValueError("INVALID_ARGUMENT")
    if type(projection) is not str or projection not in ("active","tombstoned","superseded","quarantined","unknown"): raise ValueError("INVALID_ARGUMENT")
    if type(negative) is not str or negative not in BASES: raise ValueError("INVALID_ARGUMENT")
    if negative == "fresh_unseen": raise ValueError("ADMISSION_IS_NOT_RECOVERY")
    if conflict:
        return envelope(rid,scope,"unknown","INTEGRITY_FAILURE","query_same_token",dict(commit_status="unknown",audit="unknown",projection="unknown",negative_basis="unassessed"))
    if status != "absent" and negative != "unassessed": raise ValueError("INVALID_ARGUMENT")
    if status == "absent" and negative == "unassessed": status="unknown"
    target=dict(commit_status=status,audit=audit,projection=projection if content_allowed and status == "committed" else "unknown",negative_basis=negative)
    if status == "unknown":
        target.update(audit="unknown",projection="unknown",negative_basis="unassessed")
        return envelope(rid,scope,"unknown","RECOVERY_UNCERTAIN","query_same_token",target)
    if status == "absent":
        target["audit"]="unknown"
        if negative == "durable_cancel": return envelope(rid,scope,"error","CANCELLED","return_original_cancel",target)
        if negative == "preaccept_rejected": return envelope(rid,scope,"error","PREACCEPT_REJECTED","return_original_rejection",target)
        raise ValueError("INVALID_ENVELOPE")
    if audit != "ok":
        code={"missing":"AUDIT_INCOMPLETE","failed":"AUDIT_FAILED","unknown":"AUDIT_UNCERTAIN"}[audit]
        return envelope(rid,scope,"error",code,"reconcile_audit",target)
    return envelope(rid,scope,"ok",None,"return_original",target)

def validate_envelope(value):
    _json_domain(value)
    schema=parse((ROOT/"spec/response.schema.json").read_text(encoding="utf-8"));check_schema(schema);_validate(value,schema,schema)
    t=value["target"];key=(value["outcome"],value["error_code"],value["next_action"])
    if t is None:
        allowed={("error","NOT_FOUND_OR_DENIED","authenticate")}
        if value["scope"] == "read": allowed |= {("ok",None,"none"),("error","READ_FAILED","retry_read")}
    else:
        if value["scope"] == "read": raise ValueError("INVALID_ENVELOPE")
        status,audit,negative=t["commit_status"],t["audit"],t["negative_basis"]
        if status == "unknown":
            allowed={("unknown","RECOVERY_UNCERTAIN","query_same_token"),("unknown","INTEGRITY_FAILURE","query_same_token")}
            if audit != "unknown" or t["projection"] != "unknown" or negative != "unassessed": raise ValueError("INVALID_ENVELOPE")
        elif status == "absent":
            mapping={"durable_cancel":("error","CANCELLED","return_original_cancel"),"preaccept_rejected":("error","PREACCEPT_REJECTED","return_original_rejection")}
            allowed={mapping[negative]} if negative in mapping else set()
            if t["projection"] != "unknown" or audit != "unknown": raise ValueError("INVALID_ENVELOPE")
        else:
            if negative != "unassessed": raise ValueError("INVALID_ENVELOPE")
            if audit == "ok": allowed={("ok",None,"return_original")}
            else: allowed={("error",{"missing":"AUDIT_INCOMPLETE","failed":"AUDIT_FAILED","unknown":"AUDIT_UNCERTAIN"}[audit],"reconcile_audit")}
        if key not in allowed: raise ValueError("INVALID_ENVELOPE")
    if key not in allowed: raise ValueError("INVALID_ENVELOPE")
    return copy.deepcopy(value)
