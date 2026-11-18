"""Unified v2 API request, full-response, untrusted-record, and cancel contract validators."""
from __future__ import annotations
import copy
import hashlib
from framework.api import _json_domain, _validate, check_reader_order, check_schema
from framework.conditions import condition_space
from framework.migration import instant, time_bundle
from framework.spec import ROOT, canonical, parse

_SCHEMA_CACHE: dict[str, tuple[tuple[int, int], dict]] = {}

# Disallow bidirectional override / mark / zero-width spoofing controls in untrusted bodies.
_FORBIDDEN_BODY_CONTROLS = frozenset(
    [0x061C]
    + list(range(0x200B, 0x2010))
    + [0x2060, 0xFEFF]
    + list(range(0x202A, 0x202F))
    + list(range(0x2066, 0x206A))
)


def _load_cached_schema(rel_path: str) -> dict:
    p = ROOT / rel_path
    st = p.stat()
    sig = (st.st_mtime_ns, st.st_size)
    cached = _SCHEMA_CACHE.get(rel_path)
    if cached is not None and cached[0] == sig:
        schema = copy.deepcopy(cached[1])
        check_schema(schema)
        return schema
    schema = parse(p.read_text(encoding="utf-8"))
    check_schema(schema)
    _SCHEMA_CACHE[rel_path] = (sig, schema)
    return copy.deepcopy(schema)


def _schema_to_condition_space(raw: dict) -> dict:
    attrs: dict[str, str] = {}
    for item in raw["attributes"]:
        k, v = item["key"], item["value"]
        if k in attrs:
            raise ValueError("CONFLICTING_CONDITION")
        attrs[k] = v
    return condition_space({
        "carrier": raw["carrier"],
        "method": raw["method"],
        "existence": raw["existence"],
        "attributes": attrs,
    })


def validate_v2_request(value: object) -> dict:
    """Validate a v2 API request (Write/Read/Govern/Cancel/SelfCheck) with unified Condition & BiTemporal."""
    try:
        _json_domain(value)
        encoded = canonical(value)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("INVALID_ARGUMENT: encoding/depth") from exc
    if len(encoded) > 131072:
        raise ValueError("INVALID_ARGUMENT: request bytes")
    schema = _load_cached_schema("spec/api_v2.schema.json")
    _validate(value, schema, schema)
    check_reader_order(value)
    out = copy.deepcopy(value)
    kind = out["kind"]
    if kind in ("Write.create", "Write.modify"):
        _schema_to_condition_space(out["condition_space"])
        time_bundle(out["bitemporal"])
    elif kind == "Govern.correct_revision":
        _schema_to_condition_space(out["replacement"]["condition_space"])
        time_bundle(out["replacement"]["bitemporal"])
    elif kind in ("Read.get", "Read.search", "Read.expand"):
        _schema_to_condition_space(out["condition_query"])
        instant(out["time_point"])
    return out


def extract_condition_space(raw_schema_cond: dict) -> dict:
    """Convert schema condition_space object (sorted attributes array) to evaluator dict."""
    return _schema_to_condition_space(raw_schema_cond)


def contains_spoofing_controls(text: str) -> bool:
    return any(ord(ch) in _FORBIDDEN_BODY_CONTROLS for ch in text)


def build_untrusted_record(locator: dict, body: str, provenance: dict | None = None) -> dict:
    """Wrap body in explicit untrusted_markdown envelope and verify SHA256."""
    if type(body) is not str or not 1 <= len(body) <= 65536:
        raise ValueError("INVALID_ARGUMENT: body")
    body.encode("utf-8", errors="strict")
    if contains_spoofing_controls(body):
        raise ValueError("INVALID_ARGUMENT: control_spoof")
    body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if type(locator) is not dict or locator.get("content_sha") != body_sha:
        raise ValueError("INTEGRITY_FAILURE")
    return {
        "content_type": "untrusted_markdown",
        "locator": copy.deepcopy(locator),
        "body": body,
        "body_sha": body_sha,
        "condition_verdict": "MATCH",
        "temporal_verdict": "MATCH",
        "provenance": copy.deepcopy(provenance),
    }


def validate_full_response(value: object) -> dict:
    """Validate a 0.2-full response envelope and enforce security/semantic invariants."""
    _json_domain(value)
    schema = _load_cached_schema("spec/response_full.schema.json")
    _validate(value, schema, schema)
    scope = value["scope"]
    outcome = value["outcome"]
    code = value["error_code"]
    records = value["records"]
    target = value["target"]
    receipt = value["historical_receipt"]
    agg = value["selfcheck_aggregate"]

    if outcome == "ok" and code is not None:
        raise ValueError("INVALID_ENVELOPE: ok cannot carry error_code")
    if outcome != "ok" and code is None:
        raise ValueError("INVALID_ENVELOPE: non-ok must carry error_code")
    if scope == "read":
        if target is not None:
            raise ValueError("INVALID_ENVELOPE: target forbidden on read")
    if records is not None:
        if scope != "read" or outcome != "ok":
            raise ValueError("INVALID_ENVELOPE: records forbidden outside ok read")
        for rec in records:
            expected_sha = hashlib.sha256(rec["body"].encode("utf-8")).hexdigest()
            if rec["body_sha"] != expected_sha or rec["locator"]["content_sha"] != expected_sha:
                raise ValueError("INVALID_ENVELOPE: record sha mismatch")
            if contains_spoofing_controls(rec["body"]):
                raise ValueError("INVALID_ENVELOPE: control_spoof")
    if value["next_cursor"] is not None and (scope != "read" or outcome != "ok"):
        raise ValueError("INVALID_ENVELOPE: next_cursor forbidden outside ok read")
    if scope == "read" and outcome == "ok" and (value["snapshot_ref"] is None or value["policy_generation"] is None):
        raise ValueError("INVALID_ENVELOPE: ok read requires snapshot_ref and policy_generation")
    if scope == "selfcheck":
        if agg is None or records is not None:
            raise ValueError("INVALID_ENVELOPE: selfcheck shape")
    elif agg is not None:
        raise ValueError("INVALID_ENVELOPE: aggregate only for selfcheck")
    if scope == "cancel" and outcome == "error" and code == "CANCELLED":
        if target is None or target["commit_status"] != "absent" or target["negative_basis"] != "durable_cancel":
            raise ValueError("INVALID_ENVELOPE: cancel semantics")
    if receipt is not None and scope not in ("mutation", "receipt"):
        raise ValueError("INVALID_ENVELOPE: receipt scope")
    if code == "NOT_FOUND_OR_DENIED" and (records is not None or target is not None or receipt is not None):
        raise ValueError("INVALID_ENVELOPE: denied response must not disclose target/records/receipt")
    return copy.deepcopy(value)
