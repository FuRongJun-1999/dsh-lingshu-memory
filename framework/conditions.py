"""Unified Condition Space and BiTemporal pure evaluators (not a runtime)."""
from __future__ import annotations
import copy
from framework.api import _json_domain
from framework.migration import time_bundle, time_match
from framework.spec import canonical

SLOTS = ("carrier", "method", "existence")


def _check_text(value: object, max_len: int, code: str) -> str:
    if type(value) is not str or not 1 <= len(value) <= max_len:
        raise ValueError(code)
    value.encode("utf-8", errors="strict")
    return value


def _check_slot(slot: object) -> dict:
    if type(slot) is not dict or type(slot.get("state")) is not str:
        raise ValueError("INVALID_CONDITION")
    state = slot["state"]
    if state == "unknown":
        if set(slot) != {"state"}:
            raise ValueError("INVALID_CONDITION")
        return {"state": "unknown"}
    if state == "declared":
        if set(slot) != {"state", "text"}:
            raise ValueError("INVALID_CONDITION")
        return {"state": "declared", "text": _check_text(slot["text"], 4096, "INVALID_CONDITION")}
    raise ValueError("INVALID_CONDITION")


def _check_attributes(attrs: object) -> dict[str, str]:
    if type(attrs) is not dict or len(attrs) > 32:
        raise ValueError("INVALID_CONDITION")
    out: dict[str, str] = {}
    for k in sorted(attrs):
        v = attrs[k]
        _check_text(k, 128, "INVALID_CONDITION")
        _check_text(v, 128, "INVALID_CONDITION")
        out[k] = v
    return out


def condition_space(value: object) -> dict:
    """Validate and copy a unified condition space: 3 slots + string attributes."""
    _json_domain(value)
    if type(value) is not dict or set(value) != {"carrier", "method", "existence", "attributes"}:
        raise ValueError("CONDITION_REQUIRED")
    out = {slot: _check_slot(value[slot]) for slot in SLOTS}
    out["attributes"] = _check_attributes(value["attributes"])
    if len(canonical(out)) > 131072:
        raise ValueError("INVALID_CONDITION")
    return copy.deepcopy(out)


def normalize_conditions(raw: object) -> dict:
    """Normalize legacy list[str], dict[str, str], or unified dict without fabricating declared slots."""
    _json_domain(raw)
    if type(raw) is dict and set(raw) == {"carrier", "method", "existence", "attributes"}:
        return condition_space(raw)
    if type(raw) is dict and set(raw) == set(SLOTS):
        out = {slot: _check_slot(raw[slot]) for slot in SLOTS}
        out["attributes"] = {}
        return out
    attrs: dict[str, str] = {}
    if type(raw) is dict:
        attrs = _check_attributes(raw)
    elif type(raw) is list:
        if len(raw) > 32:
            raise ValueError("INVALID_CONDITION")
        for item in raw:
            _check_text(item, 1024, "INVALID_CONDITION")
            if "=" not in item:
                raise ValueError("INVALID_CONDITION")
            k, v = item.split("=", 1)
            _check_text(k, 128, "INVALID_CONDITION")
            _check_text(v, 128, "INVALID_CONDITION")
            if k in attrs:
                raise ValueError("CONFLICTING_CONDITION")
            attrs[k] = v
    else:
        raise ValueError("INVALID_CONDITION")
    return {
        "carrier": {"state": "unknown"},
        "method": {"state": "unknown"},
        "existence": {"state": "unknown"},
        "attributes": {k: attrs[k] for k in sorted(attrs)},
    }


def condition_match(record_cond: object, query_cond: object, *, required_slots: tuple[str, ...] = SLOTS) -> str:
    """Tri-state condition evaluation: NO_MATCH > DEFER > MATCH.

    Never returns MATCH for unknown == unknown, empty required_slots, or missing required attributes.
    """
    rec = condition_space(record_cond)
    req = condition_space(query_cond)
    if type(required_slots) is not tuple or not required_slots or any(s not in SLOTS for s in required_slots):
        raise ValueError("INVALID_CONDITION")
    saw_defer = False
    slots_to_check = set(required_slots)
    for slot in SLOTS:
        if req[slot]["state"] == "declared" or rec[slot]["state"] == "declared":
            slots_to_check.add(slot)
    for slot in SLOTS:
        if slot not in slots_to_check:
            continue
        r_s = rec[slot]
        q_s = req[slot]
        if r_s["state"] == "declared" and q_s["state"] == "declared":
            if r_s["text"] != q_s["text"]:
                return "NO_MATCH"
        else:
            # Either side unknown when slot is active/required -> DEFER (never MATCH).
            saw_defer = True
    for k, q_val in req["attributes"].items():
        if k not in rec["attributes"]:
            saw_defer = True
        elif rec["attributes"][k] != q_val:
            return "NO_MATCH"
    return "DEFER" if saw_defer else "MATCH"


def bitemporal_match(bundle: object, query_points: object) -> str:
    """Evaluate explicit dual-axis temporal query points without axis fallback.

    Precedence: NO_MATCH > DEFER > MATCH.
    """
    time_bundle(bundle)
    if type(query_points) is not dict or not query_points or not set(query_points) <= {"observed", "effective"}:
        raise ValueError("AXIS_REQUIRED")
    saw_defer = False
    for axis in ("observed", "effective"):
        if axis not in query_points:
            continue
        verdict = time_match(bundle, axis, query_points[axis])
        if verdict == "NO_MATCH":
            return "NO_MATCH"
        if verdict == "DEFER":
            saw_defer = True
    return "DEFER" if saw_defer else "MATCH"
