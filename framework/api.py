"""Executable API proposal, not a transport, authentication or transaction runtime."""
from __future__ import annotations
import copy
import hashlib
import pathlib
import re
from framework.spec import parse, canonical

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECK_IDS = tuple(["C%02d" % i for i in range(1, 11)] + ["R%02d" % i for i in range(1, 10)])


def _json_domain(v, depth=0, counter=None):
    counter = [0] if counter is None else counter
    counter[0] += 1
    if depth > 24 or counter[0] > 10000:
        raise ValueError("INVALID_ARGUMENT: JSON complexity")
    if v is None or type(v) is bool:
        return
    if type(v) is int and abs(v) <= 9007199254740991:
        return
    if type(v) is str:
        v.encode("utf-8", errors="strict")
        return
    if type(v) is list:
        for x in v: _json_domain(x, depth + 1, counter)
        return
    if type(v) is dict and all(type(k) is str for k in v):
        for k, x in v.items():
            k.encode("utf-8", errors="strict")
            _json_domain(x, depth + 1, counter)
        return
    raise ValueError("INVALID_ARGUMENT: JSON domain")


def _validate(v, rule, root):
    if "$ref" in rule:
        ref = rule["$ref"]
        if not ref.startswith("#/$defs/"):
            raise ValueError("unsupported schema reference")
        return _validate(v, root["$defs"][ref[8:]], root)
    if "oneOf" in rule:
        matches = 0
        for option in rule["oneOf"]:
            try:
                _validate(v, option, root)
                matches += 1
            except ValueError:
                pass
        if matches != 1: raise ValueError("INVALID_ARGUMENT: variant")
        return
    kind = rule.get("type")
    types = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool, "null": type(None)}
    if kind not in types or type(v) is not types[kind]:
        raise ValueError("INVALID_ARGUMENT: type")
    if "const" in rule and (type(v) is not type(rule["const"]) or v != rule["const"]):
        raise ValueError("INVALID_ARGUMENT: constant")
    if "enum" in rule and not any(type(v) is type(x) and v == x for x in rule["enum"]):
        raise ValueError("INVALID_ARGUMENT: enumeration")
    if kind == "object":
        props = rule["properties"]
        if set(v) - set(props) or set(rule["required"]) - set(v):
            raise ValueError("INVALID_ARGUMENT: unknown/missing field")
        for key, value in v.items(): _validate(value, props[key], root)
    if kind == "array":
        if not rule.get("minItems", 0) <= len(v) <= rule.get("maxItems", 10000):
            raise ValueError("INVALID_ARGUMENT: array length")
        if rule.get("uniqueItems") and len({canonical(x) for x in v}) != len(v):
            raise ValueError("INVALID_ARGUMENT: duplicate item")
        for x in v: _validate(x, rule["items"], root)
    if kind == "string":
        if not rule.get("minLength", 0) <= len(v) <= rule.get("maxLength", 1048576):
            raise ValueError("INVALID_ARGUMENT: string length")
        if "pattern" in rule and re.fullmatch(rule["pattern"], v) is None:
            raise ValueError("INVALID_ARGUMENT: string format")
    if kind == "integer" and not rule.get("minimum", -9007199254740991) <= v <= rule.get("maximum", 9007199254740991):
        raise ValueError("INVALID_ARGUMENT: integer range")


def load_schema():
    return parse((ROOT / "spec/api.schema.json").read_text(encoding="utf-8"))



def check_schema(rule):
    """Reject unsupported schema keywords, rather than silently ignoring constraints."""
    allowed = {"$schema", "$id", "$defs", "title", "description", "$ref", "oneOf", "type", "properties", "required", "additionalProperties", "const", "enum", "minItems", "maxItems", "uniqueItems", "items", "minLength", "maxLength", "pattern", "minimum", "maximum"}
    if type(rule) is not dict or set(rule) - allowed:
        raise ValueError("unsupported schema vocabulary")
    typed = {"object": {"properties", "required", "additionalProperties"}, "array": {"items", "minItems", "maxItems", "uniqueItems"}, "string": {"minLength", "maxLength", "pattern"}, "integer": {"minimum", "maximum"}, "boolean": set(), "null": set()}
    meta = {"$schema", "$id", "$defs", "title", "description"}
    if "$ref" in rule: scoped = meta | {"$ref"}
    elif "oneOf" in rule: scoped = meta | {"oneOf"}
    else:
        kind = rule.get("type")
        if type(kind) is not str or kind not in typed: raise ValueError("unsupported schema type")
        scoped = meta | {"type", "const", "enum"} | typed[kind]
    if set(rule) - scoped: raise ValueError("unsupported schema keyword placement")
    for key in ("minItems", "maxItems", "minLength", "maxLength", "minimum", "maximum"):
        if key in rule and type(rule[key]) is not int: raise ValueError("invalid schema bound")
    if "uniqueItems" in rule and type(rule["uniqueItems"]) is not bool: raise ValueError("invalid uniqueItems")
    for item in rule.get("$defs", {}).values(): check_schema(item)
    for item in rule.get("oneOf", []): check_schema(item)
    for item in rule.get("properties", {}).values(): check_schema(item)
    if "items" in rule: check_schema(rule["items"])
    if rule.get("type") == "object" and rule.get("additionalProperties") is not False:
        raise ValueError("schema object must be closed")


def check_reader_order(value):
    if type(value) is dict:
        for key, item in value.items():
            if key == "reader_ceiling" and item != sorted(item):
                raise ValueError("INVALID_ARGUMENT: readers must be sorted")
            check_reader_order(item)
    elif type(value) is list:
        for item in value: check_reader_order(item)


def validate_request(value):
    try:
        _json_domain(value)
        encoded = canonical(value)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("INVALID_ARGUMENT: encoding/depth") from exc
    if len(encoded) > 131072:
        raise ValueError("INVALID_ARGUMENT: request bytes")
    schema = load_schema()
    check_schema(schema)
    _validate(value, schema, schema)
    check_reader_order(value)
    return copy.deepcopy(value)


def parse_request(text):
    try:
        if type(text) is not str or len(text.encode("utf-8")) > 131072:
            raise ValueError("INVALID_ARGUMENT: request bytes")
        return validate_request(parse(text))
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("INVALID_ARGUMENT: encoding/depth") from exc


def request_digest(value):
    return hashlib.sha256(canonical(validate_request(value))).hexdigest()


def query_digest(value):
    value = validate_request(value)
    if value["kind"] not in ("Read.search", "Read.expand"):
        raise ValueError("INVALID_ARGUMENT: not pageable")
    value.pop("cursor", None)
    return hashlib.sha256(canonical(value)).hexdigest()


# These pure predicates ASSUME their context/evidence was authenticated elsewhere.
CURSOR_FIELDS = {"tenant", "principal", "read_kind", "query_sha", "snapshot", "policy_generation"}


def cursor_valid(cursor, binding, now):
    if type(cursor) is not dict or type(binding) is not dict:
        return False
    if set(binding) != CURSOR_FIELDS or set(cursor) != CURSOR_FIELDS | {"expires_at"}:
        return False
    if type(now) is not int or now < 0 or type(cursor["expires_at"]) is not int:
        return False
    if not now < cursor["expires_at"] <= 9007199254740991:
        return False
    for field in CURSOR_FIELDS:
        a, b = cursor[field], binding[field]
        if field == "policy_generation":
            if type(a) is not int or type(b) is not int or min(a, b) < 0 or max(a, b) > 9007199254740991: return False
        elif type(a) is not str or type(b) is not str or not a or not b:
            return False
        if a != b: return False
    return binding["read_kind"] in ("Read.search", "Read.expand") and re.fullmatch("[0-9a-f]{64}", binding["query_sha"]) is not None


def receipt_scope_allowed(context, record_scope, operation, token):
    if type(context) is not dict or set(context) != {"tenant", "principal"}:
        return False
    if type(record_scope) is not tuple or len(record_scope) != 4:
        return False
    values = (context["tenant"], context["principal"], operation, token)
    return all(type(v) is str and v for v in values) and all(type(v) is str for v in record_scope) and values == record_scope


def retry_action(commit_status, same_fingerprint, history_complete):
    if type(same_fingerprint) is not bool or type(history_complete) is not bool:
        raise ValueError("INVALID_ARGUMENT")
    if type(commit_status) is not str or commit_status not in ("committed", "absent", "unknown"):
        raise ValueError("INVALID_ARGUMENT")
    if not history_complete or commit_status == "unknown": return "query_only"
    if not same_fingerprint: return "conflict"
    return "return_original" if commit_status == "committed" else "eligible_for_authorized_first_apply"


def govern_transition(state, current_revision, expected_revision, action, authorized, policy_safe, proof_fresh):
    if type(state) is not str or state not in ("active", "tombstoned", "superseded", "quarantined"):
        raise ValueError("INVALID_ARGUMENT")
    if any(type(v) is not bool for v in (authorized, policy_safe, proof_fresh)):
        raise ValueError("INVALID_ARGUMENT")
    if any(type(v) is not int or not 1 <= v <= 9007199254740991 for v in (current_revision, expected_revision)):
        raise ValueError("INVALID_ARGUMENT")
    if type(action) is not str or action not in ("forget", "restore", "correct_revision", "change_policy"):
        raise ValueError("INVALID_ARGUMENT")
    if not authorized: raise ValueError("NOT_FOUND_OR_DENIED")
    if current_revision != expected_revision: raise ValueError("REVISION_CONFLICT")
    allowed = {("active", "forget"): ("tombstoned",), ("tombstoned", "restore"): ("active",),
               ("active", "correct_revision"): ("superseded", "new_active"), ("active", "change_policy"): ("active",)}
    if (state, action) not in allowed: raise ValueError("STATE_CONFLICT")
    if action in ("restore", "correct_revision", "change_policy") and not policy_safe:
        raise ValueError("POLICY_WIDENING_UNSUPPORTED")
    if action == "restore" and not proof_fresh: raise ValueError("VERIFICATION_REQUIRED")
    return allowed[state, action]


def aggregate_checks(required, checks):
    if type(required) is not list or not required or any(type(x) is not str or x not in CHECK_IDS for x in required) or len(required) != len(set(required)):
        raise ValueError("INVALID_ARGUMENT")
    if type(checks) is not list: raise ValueError("INVALID_ARGUMENT")
    seen = {}
    for item in checks:
        if type(item) is not dict or set(item) != {"id", "status"}: raise ValueError("INVALID_ARGUMENT")
        key, status = item["id"], item["status"]
        if type(key) is not str or key not in CHECK_IDS or key in seen or type(status) is not str or status not in ("PASS", "FAIL", "NOT_RUN"):
            raise ValueError("INVALID_ARGUMENT")
        seen[key] = status
    if "FAIL" in seen.values(): return "FAIL"
    if any(seen.get(key, "NOT_RUN") != "PASS" for key in required): return "NOT_RUN"
    return "PASS"
