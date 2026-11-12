"""Strict JSON loader and supported rule vocabulary (not a runtime)."""
from __future__ import annotations
import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]

def unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key: " + key)
        out[key] = value
    return out

def parse(text):
    return json.loads(text, object_pairs_hook=unique_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))

def keys(value, expected, path):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError("unknown/missing fields: " + path)

def exact(value, expected, path):
    if type(value) is not type(expected):
        raise ValueError("unsupported rule type: " + path)
    if isinstance(expected, list):
        if len(value) != len(expected):
            raise ValueError("unsupported rule: " + path)
        for index, item in enumerate(expected):
            exact(value[index], item, path + "." + str(index))
    elif value != expected:
        raise ValueError("unsupported rule: " + path)

# This is the model's supported vocabulary, not a second normative document.
# Expanding it requires independent examples and an ADR; unknown semantics fail closed.
SUPPORTED = {
    "sensitivity": {"levels": [0, 1, 2, 3], "max": 3, "inherit_relation": "derived",
        "aggregate": "max", "clearance_operator": "gte",
        "dangling_relations": ["derived", "corroborating", "contradicting", "unknown"],
        "unknown_to_max": True, "invalid_to_quarantine": True},
    "formation": {"quantifier": "any", "relation": "derived", "true_result": "derived", "false_result": "direct"},
    "edges": {"relations": ["derived", "corroborating", "contradicting", "unknown"],
        "cross_tenant": "reject", "bind_target": ["node_id", "revision", "content_sha"],
        "mutation": "reject", "correction": "new_revision", "cycles": "reject",
        "scope_composition": "intersection", "policy_tightening": "immediate",
        "policy_widening": "bounded_by_creation"},
    "recovery": {"states": ["committed", "absent", "unknown"], "empty_after_restart": "unknown",
        "absent_requires": "authoritative_preaccept_rejection_or_durable_cancellation_without_conflict",
        "process_power_loss": "arbitrary_subset", "power_claim_requires": "platform_evidence",
        "receipt_is": "historical_commit_not_current_visibility"},
    "idempotency": {"scope": ["tenant", "principal", "operation", "token"],
        "same_fingerprint": "return_original", "different_fingerprint": "reject",
        "incomplete_history": "unknown_block_retry", "forget_releases_token": False},
    "verification": {"bind": ["subject_revision", "subject_content_sha", "scope", "method", "credential", "verified_at"],
        "source_identity_operator": "ne", "source_identity_operands": ["verifier_id", "source_id"],
        "content_change": "invalidate", "truth_assurance": "not_claimed",
        "independence_without_evidence": "unassessed"},
}

def validate(spec):
    keys(spec, ["schema_version", "spec_version", "status", "runtime_released", "application_contracts", *SUPPORTED], "root")
    exact(spec["schema_version"], 1, "schema_version")
    if type(spec["spec_version"]) is not str or not re.fullmatch(r"0\.[0-9]+\.[0-9]+", spec["spec_version"]):
        raise ValueError("invalid design spec version")
    exact(spec["status"], "design-development", "status")
    exact(spec["runtime_released"], False, "runtime_released")
    exact(spec["application_contracts"], ["Write", "Read", "Govern", "SelfCheck"], "application_contracts")
    for section, expected in SUPPORTED.items():
        keys(spec[section], expected, section)
        for field, value in expected.items():
            exact(spec[section][field], value, section + "." + field)
    return spec

def load(path=None):
    return validate(parse(pathlib.Path(path or ROOT / "spec/core.json").read_text(encoding="utf-8")))

def canonical(value):
    # No floating-point or unordered application fields are accepted in core.json.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()
