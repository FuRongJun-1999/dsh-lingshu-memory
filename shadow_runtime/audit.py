"""Payload-free hash-chained JSONL audit log and strict integrity inspector."""
from __future__ import annotations
import hashlib
import json
import pathlib
import re
from framework.spec import canonical, parse
from shadow_runtime.durability import append_line_durable
from shadow_runtime.writer_status import _name

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_KEYS = {"writer_id", "seq", "ts", "tenant", "principal", "op", "node_id", "revision", "payload_sha", "prev_sha", "entry_sha"}


def _entry_sha(entry_without_sha: dict) -> str:
    return hashlib.sha256(canonical(entry_without_sha)).hexdigest()


def _valid_audit_types(obj: dict) -> bool:
    if type(obj["seq"]) is not int or obj["seq"] < 1:
        return False
    if type(obj["ts"]) is not int or obj["ts"] < 0:
        return False
    if type(obj["revision"]) is not int or obj["revision"] < 1:
        return False
    try:
        _name(obj["writer_id"])
    except ValueError:
        return False
    for k in ("tenant", "principal", "op", "node_id"):
        if type(obj[k]) is not str or not obj[k]:
            return False
    for k in ("payload_sha", "prev_sha", "entry_sha"):
        if type(obj[k]) is not str or _HEX64.fullmatch(obj[k]) is None:
            return False
    return True


def inspect_audit(audit_path: pathlib.Path, *, expected_tenant: str | None = None) -> dict:
    """Strictly distinguish missing, ok, degraded (truncated/malformed tail), and integrity_failure."""
    p = pathlib.Path(audit_path)
    if not p.exists():
        return {"state": "missing", "count": 0, "last_seq": 0, "last_sha": "0" * 64, "foreign_rows": 0}
    try:
        raw_bytes = p.read_bytes()
    except OSError:
        return {"state": "integrity_failure", "reason": "unreadable_audit", "count": 0, "last_seq": 0, "last_sha": "0" * 64, "foreign_rows": 0}
    if not raw_bytes:
        return {"state": "missing", "count": 0, "last_seq": 0, "last_sha": "0" * 64, "foreign_rows": 0}

    has_trailing_nl = raw_bytes.endswith(b"\n")
    raw_lines = raw_bytes.split(b"\n")
    if has_trailing_nl:
        raw_lines = raw_lines[:-1]

    prev_sha = "0" * 64
    seq = 0
    foreign_rows = 0
    total = len(raw_lines)
    for idx, raw_line in enumerate(raw_lines, 1):
        is_last = idx == total
        try:
            line = raw_line.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            if is_last:
                return {"state": "degraded", "reason": "malformed_tail_utf8", "count": idx - 1, "last_seq": seq, "last_sha": prev_sha, "foreign_rows": foreign_rows}
            return {"state": "integrity_failure", "reason": "corrupt_middle_utf8", "count": idx - 1, "last_seq": seq, "last_sha": prev_sha, "foreign_rows": foreign_rows}

        if is_last and not has_trailing_nl:
            return {"state": "degraded", "reason": "truncated_tail", "count": idx - 1, "last_seq": seq, "last_sha": prev_sha, "foreign_rows": foreign_rows}

        try:
            obj = parse(line)
        except Exception:
            if is_last:
                return {"state": "degraded", "reason": "malformed_tail_json", "count": idx - 1, "last_seq": seq, "last_sha": prev_sha, "foreign_rows": foreign_rows}
            return {"state": "integrity_failure", "reason": "corrupt_middle_line", "count": idx - 1, "last_seq": seq, "last_sha": prev_sha, "foreign_rows": foreign_rows}

        if type(obj) is not dict:
            return {"state": "integrity_failure", "reason": "invalid_audit_schema", "count": idx - 1, "last_seq": seq, "last_sha": prev_sha, "foreign_rows": foreign_rows}
        # Check payload leakage BEFORE strict key-set rejection so leak is classified explicitly!
        if "body" in obj or "content" in obj:
            return {"state": "integrity_failure", "reason": "payload_leak_in_audit", "count": idx - 1, "last_seq": seq, "last_sha": prev_sha, "foreign_rows": foreign_rows}
        if set(obj) != _EXPECTED_KEYS or not _valid_audit_types(obj):
            return {"state": "integrity_failure", "reason": "invalid_audit_schema", "count": idx - 1, "last_seq": seq, "last_sha": prev_sha, "foreign_rows": foreign_rows}
        if obj["seq"] != seq + 1 or obj["prev_sha"] != prev_sha:
            return {"state": "integrity_failure", "reason": "hash_chain_break", "count": idx - 1, "last_seq": seq, "last_sha": prev_sha, "foreign_rows": foreign_rows}
        body_check = {k: v for k, v in obj.items() if k != "entry_sha"}
        if _entry_sha(body_check) != obj["entry_sha"]:
            return {"state": "integrity_failure", "reason": "entry_sha_mismatch", "count": idx - 1, "last_seq": seq, "last_sha": prev_sha, "foreign_rows": foreign_rows}
        if expected_tenant is not None and obj["tenant"] != expected_tenant:
            foreign_rows += 1
        seq = obj["seq"]
        prev_sha = obj["entry_sha"]
    if foreign_rows > 0:
        return {"state": "integrity_failure", "reason": "foreign_tenant_row", "count": seq, "last_seq": seq, "last_sha": prev_sha, "foreign_rows": foreign_rows}
    return {"state": "ok", "count": seq, "last_seq": seq, "last_sha": prev_sha, "foreign_rows": 0}


class PayloadFreeAuditLog:
    """Append-only payload-free hash-chained JSONL audit log."""

    def __init__(self, audit_path: pathlib.Path):
        self.path = pathlib.Path(audit_path)

    def append(self, *, writer_id: str, ts: int, tenant: str, principal: str, op: str, node_id: str,
               revision: int, payload_sha: str, durable: bool, fault_hook=None) -> dict:
        info = inspect_audit(self.path)
        if info["state"] not in ("ok", "missing"):
            raise ValueError("AUDIT_CORRUPTED:" + info["state"])
        seq = info["last_seq"] + 1
        prev_sha = info["last_sha"]
        entry = {
            "writer_id": _name(writer_id),
            "seq": seq,
            "ts": ts,
            "tenant": tenant,
            "principal": principal,
            "op": op,
            "node_id": node_id,
            "revision": revision,
            "payload_sha": payload_sha,
            "prev_sha": prev_sha,
        }
        entry["entry_sha"] = _entry_sha(entry)
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        append_line_durable(self.path, line, durable=durable, fault_hook=fault_hook)
        return entry
