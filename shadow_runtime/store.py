"""Plain-text Markdown truth + JSON structured index/WAL/fencing shadow runtime (NO binary DB)."""
from __future__ import annotations
import copy
import hashlib
import json
import os
import pathlib
import time
import uuid
from shadow_runtime.writer_status import WriterStatus, _name
from dataclasses import replace
from framework.api import cursor_valid, govern_transition, receipt_scope_allowed, retry_action
from framework.conditions import bitemporal_match, condition_match
from framework.contracts import build_untrusted_record, extract_condition_space, validate_full_response, validate_v2_request
from framework.migration import time_bundle
from framework.model import Edge, EpochDecisionCache, Model, Node, RecoveryEvidence, can_read_with_epoch_cache, recover, request_fingerprint, verification_eligible
from framework.responses import absence_basis, cancellation
from framework.read_get import ReadSnapshot, read_get
from framework.security import binding_shape, context_shape, emit_allowed
from framework.spec import canonical, parse
from framework.read_search import read_search
from sandbox_runtime.store import wordset
from shadow_runtime.audit import PayloadFreeAuditLog, inspect_audit
from shadow_runtime.durability import ExclusiveFileLock, atomic_write_text, ensure_dir_durable, probe_platform_durability


class InjectedCrash(BaseException):
    """Simulated SIGKILL / power cut at an explicit transaction boundary."""


def _sha_obj(obj: object) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


_META_FIELDS = frozenset({
    "node_id", "revision", "tenant", "content_sha", "declared_sensitivity",
    "creation_readers", "current_readers", "source_edges", "condition_space",
    "bitemporal", "source_attribution", "state",
})


def _seal_meta(value: dict) -> dict:
    body = {k: copy.deepcopy(v) for k, v in value.items() if k != "meta_sha"}
    if set(body) != _META_FIELDS:
        raise ValueError("INTEGRITY_FAILURE: invalid meta fields")
    body["meta_sha"] = _sha_obj(body)
    return body


def _node_dir_key(node_id: str) -> str:
    return hashlib.sha256(node_id.encode("utf-8")).hexdigest()[:32]


def _token_key_sha(tenant: str, principal: str, operation: str, token: str) -> str:
    return hashlib.sha256(canonical([tenant, principal, operation, token])).hexdigest()


class ShadowMarkdownStore:
    """Plain-text MD + JSON shadow runtime implementing M4/M5 transaction, recovery, and R01-R09 contracts.

    Truth source: nodes/<sha32>/rev_NNNNNN.md (immutable verbatim UTF-8 markdown) + rev_NNNNNN.meta.json
    Idempotency & Fencing: tokens/<key_sha>.json + intents/<tx_id>.json
    Derived projections: manifest.json (atomically swapped), index/inverted.json (rebuildable)
    Audit: audit/audit.jsonl (payload-free hash-chained JSONL)
    """

    def __init__(self, root_dir: str | pathlib.Path, *, synthetic: bool,
                 durability_probe_fn=probe_platform_durability, lock_timeout_s: float = 5.0, writer_handle=None):
        if synthetic is not True:
            raise ValueError("EXPLICIT_SYNTHETIC_REQUIRED")
        self.root = pathlib.Path(root_dir).resolve()
        self.synthetic = True
        self._writer_id = ("shadow-" + uuid.uuid4().hex if writer_handle is None else
                           WriterStatus(self.root, synthetic=True).identify(writer_handle))
        self._durability_probe_fn = durability_probe_fn
        self._lock_timeout_s = float(lock_timeout_s)
        self.model = Model()
        self.cache = EpochDecisionCache()
        self.audit = PayloadFreeAuditLog(self.root / "audit/audit.jsonl")
        self._lock_path = self.root / "locks/write.lock"
        self._cursors: dict[str, dict] = {}
        self._cursor_offsets: dict[str, int] = {}
        self.root.mkdir(parents=True, exist_ok=True)
        for sub in ("nodes", "tokens", "intents", "audit", "index", "locks", "verifications"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    def _lock(self) -> ExclusiveFileLock:
        return ExclusiveFileLock(self._lock_path, timeout_s=self._lock_timeout_s)

    def _probe_power(self) -> dict:
        return self._durability_probe_fn(self.root)

    def _md_path(self, node_id: str, rev: int) -> pathlib.Path:
        return self.root / "nodes" / _node_dir_key(node_id) / f"rev_{rev:06d}.md"

    def _meta_path(self, node_id: str, rev: int) -> pathlib.Path:
        return self.root / "nodes" / _node_dir_key(node_id) / f"rev_{rev:06d}.meta.json"

    def _token_path(self, tenant: str, principal: str, operation: str, token: str) -> pathlib.Path:
        return self.root / "tokens" / (_token_key_sha(tenant, principal, operation, token) + ".json")

    def _intent_path(self, tx_id: str) -> pathlib.Path:
        return self.root / "intents" / f"{tx_id}.json"

    def _manifest_path(self) -> pathlib.Path:
        return self.root / "manifest.json"

    def _index_path(self) -> pathlib.Path:
        return self.root / "index/inverted.json"

    def _read_json_strict(self, path: pathlib.Path) -> dict:
        return parse(path.read_text(encoding="utf-8"))

    def _read_meta_verified(self, path: pathlib.Path) -> dict:
        meta = self._read_json_strict(path)
        if type(meta) is not dict or set(meta) != _META_FIELDS | {"meta_sha"}:
            raise ValueError("INTEGRITY_FAILURE: meta schema")
        body = {k: v for k, v in meta.items() if k != "meta_sha"}
        if type(meta["meta_sha"]) is not str or _sha_obj(body) != meta["meta_sha"]:
            raise ValueError("INTEGRITY_FAILURE: meta sha")
        return meta

    def _write_json_atomic(self, path: pathlib.Path, obj: dict, *, durable: bool, fault_hook=None, stage: str = "json") -> None:
        text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        atomic_write_text(path, text, durable=durable, fault_hook=fault_hook, stage_prefix=stage)

    @staticmethod
    def _transaction_audit(chain_state, receipt_state):
        """A healthy chain alone cannot establish this transaction's audit result."""
        if "failed" in (chain_state, receipt_state):
            return "failed"
        if "missing" in (chain_state, receipt_state):
            return "missing"
        return "ok" if chain_state == receipt_state == "ok" else "failed"

    def _finalize_audit(self, ctx, req, receipt, now, *, durable, fault_hook, writer_id=None):
        try:
            self.audit.append(
                writer_id=self._writer_id if writer_id is None else writer_id, ts=now, tenant=ctx["tenant"], principal=ctx["principal"],
                op=req["kind"], node_id=receipt["node_id"], revision=receipt["revision"],
                payload_sha=receipt["content_sha"],
                transaction_id=_token_key_sha(ctx["tenant"], ctx["principal"], req["kind"], req["caller_token"]),
                durable=durable, fault_hook=fault_hook,
            )
        except Exception:
            receipt["audit_state"] = "failed"
        else:
            receipt["audit_state"] = "ok"
        # Receipt persistence errors propagate independently from audit I/O.
        self._save_token_record(
            ctx["tenant"], ctx["principal"], req["kind"], req["caller_token"],
            {"commit_status": "committed", "fingerprint": receipt["fingerprint"], "history_complete": True,
             "negative_basis": "unassessed", "fencing_epoch": 0, "node_id": receipt["node_id"],
             "revision": receipt["revision"], "content_sha": receipt["content_sha"], "receipt": receipt},
            durable=durable, fault_hook=fault_hook,
        )
        return receipt["audit_state"] == "ok"

    def _audit_status_norm(self, tenant: str, receipt: dict) -> str:
        st = inspect_audit(self.root / "audit/audit.jsonl", expected_tenant=tenant)["state"]
        return self._transaction_audit(st, receipt["audit_state"])

    def _intent_matches(self, path: pathlib.Path) -> tuple[dict | None, bool]:
        try:
            obj = self._read_json_strict(path)
            if type(obj) is not dict or obj.get("schema_version") != 2:
                return None, False
            required = {"schema_version", "state", "tx_id", "scope", "fingerprint", "node_id", "revision", "content_sha", "before_manifest", "before_manifest_sha", "after_manifest", "after_manifest_sha", "meta_changes", "new_md", "receipt", "timestamp", "durable", "intent_sha"}
            if set(obj) != required or type(obj["intent_sha"]) is not str:
                return None, True
            body = {k: v for k, v in obj.items() if k != "intent_sha"}
            if _sha_obj(body) != obj["intent_sha"]:
                return None, True
            if _sha_obj(obj["before_manifest"]) != obj["before_manifest_sha"] or _sha_obj(obj["after_manifest"]) != obj["after_manifest_sha"]:
                return None, True
            if obj["state"] not in ("prepared", "complete", "aborted") or type(obj["durable"]) is not bool:
                return None, True
            scope = obj["scope"]
            if type(scope) is not dict or set(scope) != {"tenant", "principal", "operation", "token"}:
                return None, True
            if _token_key_sha(scope["tenant"], scope["principal"], scope["operation"], scope["token"])[:16] != obj["tx_id"]:
                return None, True
            return obj, False
        except Exception:
            return None, True

    def _save_intent(self, intent: dict, *, fault_hook=None, stage: str = "intent") -> dict:
        sealed = copy.deepcopy(intent)
        sealed.pop("intent_sha", None)
        sealed["intent_sha"] = _sha_obj(sealed)
        self._write_json_atomic(self._intent_path(sealed["tx_id"]), sealed, durable=sealed["durable"], fault_hook=fault_hook, stage=stage)
        intent.clear()
        intent.update(sealed)
        return sealed

    def _prepare_transaction(self, *, req: dict, ctx: dict, now: int, fp: str,
                             before_manifest: dict, after_manifest: dict, meta_changes: list,
                             new_md: dict | None, receipt: dict, durable: bool,
                             fault_hook=None) -> dict:
        if not self._manifest_path().exists():
            self._save_manifest(before_manifest, durable=durable, fault_hook=None)
        token, operation = req["caller_token"], req["kind"]
        tx_id = _token_key_sha(ctx["tenant"], ctx["principal"], operation, token)[:16]
        intent = {
            "schema_version": 2, "state": "prepared", "tx_id": tx_id,
            "scope": {"tenant": ctx["tenant"], "principal": ctx["principal"], "operation": operation, "token": token},
            "fingerprint": fp, "node_id": receipt["node_id"], "revision": receipt["revision"],
            "content_sha": receipt["content_sha"], "before_manifest": copy.deepcopy(before_manifest),
            "before_manifest_sha": _sha_obj(before_manifest), "after_manifest": copy.deepcopy(after_manifest),
            "after_manifest_sha": _sha_obj(after_manifest), "meta_changes": copy.deepcopy(meta_changes),
            "new_md": copy.deepcopy(new_md), "receipt": copy.deepcopy(receipt), "timestamp": now,
            "durable": durable,
        }
        self._save_intent(intent, fault_hook=fault_hook, stage="intent")
        self._save_token_record(
            ctx["tenant"], ctx["principal"], operation, token,
            {"commit_status": "unknown", "fingerprint": fp, "history_complete": False,
             "negative_basis": "unassessed", "fencing_epoch": 0, "node_id": receipt["node_id"],
             "revision": receipt["revision"], "content_sha": receipt["content_sha"], "receipt": None},
            durable=durable, fault_hook=fault_hook,
        )
        return intent

    def _rollback_transaction(self, intent: dict) -> None:
        scope = intent["scope"]
        token, corrupt = self._load_token_record(scope["tenant"], scope["principal"], scope["operation"], scope["token"])
        pending = {"commit_status": "unknown", "fingerprint": intent["fingerprint"], "history_complete": False,
                   "negative_basis": "unassessed", "fencing_epoch": 0, "node_id": intent["node_id"],
                   "revision": intent["revision"], "content_sha": intent["content_sha"], "receipt": None}
        if corrupt or (token is not None and canonical({k: token[k] for k in pending}) != canonical(pending)):
            raise ValueError("INTEGRITY_FAILURE: token contradicts uncommitted transaction")
        # Validate all rollback inputs before the first disk mutation.
        changes = []
        for change in reversed(intent["meta_changes"]):
            path = self._meta_path(intent["node_id"], change["revision"])
            before, after = change["before"], change["after"]
            current = self._read_meta_verified(path) if path.exists() else None
            if before is None:
                if current is not None:
                    if current != after:
                        raise ValueError("INTEGRITY_FAILURE: unexpected metadata during rollback")
                    changes.append((path, None))
            elif current == before:
                continue
            elif current is None or current == after:
                changes.append((path, before))
            else:
                raise ValueError("INTEGRITY_FAILURE: metadata cannot be rolled back")
        new_md = intent["new_md"]
        if new_md is not None:
            path = self._md_path(intent["node_id"], new_md["revision"])
            if path.exists():
                if _sha_bytes(path.read_bytes()) != new_md["content_sha"]:
                    raise ValueError("INTEGRITY_FAILURE: body cannot be rolled back")
                changes.append((path, None))
        for path, before in changes:
            if before is None:
                path.unlink()
            else:
                self._write_json_atomic(path, before, durable=False, stage="rollback_meta")
        intent["state"] = "aborted"
        self._save_intent(intent, stage="intent_abort")

    def _verify_transaction_files(self, intent: dict) -> None:
        for change in intent["meta_changes"]:
            path = self._meta_path(intent["node_id"], change["revision"])
            if not path.exists() or self._read_meta_verified(path) != change["after"]:
                raise ValueError("INTEGRITY_FAILURE: committed metadata mismatch")
        new_md = intent["new_md"]
        if new_md is not None:
            path = self._md_path(intent["node_id"], new_md["revision"])
            if not path.exists() or _sha_bytes(path.read_bytes()) != new_md["content_sha"]:
                raise ValueError("INTEGRITY_FAILURE: committed body mismatch")

    def _finish_transaction(self, intent: dict, *, fault_hook=None) -> tuple[dict, bool]:
        manifest = self._load_manifest_or_init()
        if _sha_obj(manifest) != intent["after_manifest_sha"]:
            raise ValueError("INTEGRITY_FAILURE: transaction manifest is not committed")
        self._verify_transaction_files(intent)
        self._rebuild_index_locked(manifest, durable=intent["durable"], fault_hook=fault_hook)
        scope = intent["scope"]
        receipt = copy.deepcopy(intent["receipt"])
        audit_ok = self._finalize_audit(
            {"tenant": scope["tenant"], "principal": scope["principal"]},
            {"kind": scope["operation"], "caller_token": scope["token"]},
            receipt, intent["timestamp"], durable=intent["durable"], fault_hook=fault_hook, writer_id=receipt["writer_id"],
        )
        intent["state"] = "complete"
        self._save_intent(intent, fault_hook=fault_hook, stage="intent_complete")
        return receipt, audit_ok

    def _run_prepared_transaction(self, intent: dict, new_md_content: dict | None, *, fault_hook=None) -> tuple[dict, bool]:
        if intent["new_md"] is not None:
            if type(new_md_content) is not dict or new_md_content.get("revision") != intent["new_md"]["revision"]:
                raise ValueError("INTEGRITY_FAILURE: missing new revision content")
            content = new_md_content["content"]
            if _sha_bytes(content.encode("utf-8")) != intent["new_md"]["content_sha"]:
                raise ValueError("INTEGRITY_FAILURE: new revision content mismatch")
            target = self._md_path(intent["node_id"], intent["new_md"]["revision"])
            ensure_dir_durable(target.parent, durable=intent["durable"])
            atomic_write_text(target, content, durable=intent["durable"], fault_hook=fault_hook, stage_prefix="md")
        for change in intent["meta_changes"]:
            self._write_json_atomic(self._meta_path(intent["node_id"], change["revision"]), change["after"], durable=intent["durable"], fault_hook=fault_hook, stage="meta")
        self._save_manifest(intent["after_manifest"], durable=intent["durable"], fault_hook=fault_hook)
        return self._finish_transaction(intent, fault_hook=fault_hook)

    def _recover_pending_transactions(self) -> None:
        self._load_manifest_or_init()
        for path in sorted((self.root / "intents").glob("*.json")):
            intent, corrupt = self._intent_matches(path)
            if intent is None:
                if corrupt:
                    raise ValueError("INTEGRITY_FAILURE: corrupt transaction intent")
                continue
            if intent["state"] in ("complete", "aborted"):
                continue
            current = self._load_manifest_or_init()
            current_sha = _sha_obj(current)
            if current_sha == intent["before_manifest_sha"]:
                self._rollback_transaction(intent)
            elif current_sha == intent["after_manifest_sha"]:
                self._finish_transaction(intent)
            else:
                raise ValueError("INTEGRITY_FAILURE: transaction manifest diverged")

    def _load_intent_for_scope(self, tenant: str, principal: str, operation: str, token: str) -> tuple[dict | None, bool]:
        tx_id = _token_key_sha(tenant, principal, operation, token)[:16]
        ip = self._intent_path(tx_id)
        if not ip.exists():
            return None, False
        intent, corrupt = self._intent_matches(ip)
        if intent is not None:
            if intent["scope"] != {"tenant": tenant, "principal": principal, "operation": operation, "token": token}:
                return None, True
            return intent, False
        try:
            obj = self._read_json_strict(ip)
            req_keys = {"tx_id", "scope", "fingerprint", "node_id", "revision", "content_sha", "state"}
            if type(obj) is not dict or set(obj) != req_keys:
                return None, True
            if obj["scope"] != {"tenant": tenant, "principal": principal, "operation": operation, "token": token}:
                return None, True
            return obj, False
        except Exception:
            return None, True

    def _load_manifest_or_init(self) -> dict:
        mp = self._manifest_path()
        if not mp.exists():
            data_dirs = ("nodes", "intents", "verifications")
            if any((self.root / name).exists() and any(path.is_file() for path in (self.root / name).rglob("*")) for name in data_dirs):
                raise ValueError("INTEGRITY_FAILURE: missing manifest with stored records")
            return {
                "schema_version": 1,
                "node_seq": 0,
                "content_generation": 1,
                "policy_generation": 1,
                "graph_epoch": 1,
                "nodes": {},
            }
        m = self._read_json_strict(mp)
        expected = {"schema_version", "node_seq", "content_generation", "policy_generation", "graph_epoch", "nodes", "manifest_sha"}
        if type(m) is not dict or set(m) != expected:
            raise ValueError("INTEGRITY_FAILURE: manifest schema")
        body = {k: v for k, v in m.items() if k != "manifest_sha"}
        if _sha_obj(body) != m["manifest_sha"]:
            raise ValueError("INTEGRITY_FAILURE: manifest sha")
        return body

    def _save_manifest(self, manifest_body: dict, *, durable: bool, fault_hook=None) -> dict:
        out = copy.deepcopy(manifest_body)
        out["manifest_sha"] = _sha_obj(manifest_body)
        self._write_json_atomic(self._manifest_path(), out, durable=durable, fault_hook=fault_hook, stage="manifest")
        return out

    def _load_token_record(self, tenant: str, principal: str, operation: str, token: str) -> tuple[dict | None, bool]:
        """Load token ledger; returns (record, corrupted_flag)."""
        tp = self._token_path(tenant, principal, operation, token)
        if not tp.exists():
            return None, False
        try:
            obj = self._read_json_strict(tp)
            req_keys = {"scope", "key_sha", "commit_status", "fingerprint", "history_complete", "negative_basis", "fencing_epoch", "node_id", "revision", "content_sha", "receipt", "checksum"}
            if type(obj) is not dict or set(obj) != req_keys:
                return None, True
            expected_sha = _token_key_sha(tenant, principal, operation, token)
            if obj["key_sha"] != expected_sha or obj["scope"] != {"tenant": tenant, "principal": principal, "operation": operation, "token": token}:
                return None, True
            body = {k: v for k, v in obj.items() if k != "checksum"}
            if obj["commit_status"] == "committed":
                _name(obj["receipt"]["writer_id"])  # never attribute legacy receipts to the replayer
            if _sha_obj(body) != obj["checksum"]:
                return None, True
            return obj, False
        except Exception:
            return None, True

    def _save_token_record(self, tenant: str, principal: str, operation: str, token: str, fields: dict, *, durable: bool, fault_hook=None) -> dict:
        rec = {
            "scope": {"tenant": tenant, "principal": principal, "operation": operation, "token": token},
            "key_sha": _token_key_sha(tenant, principal, operation, token),
            **fields,
        }
        rec["checksum"] = _sha_obj(rec)
        self._write_json_atomic(self._token_path(tenant, principal, operation, token), rec, durable=durable, fault_hook=fault_hook, stage="token")
        return rec

    def _build_graph_nodes(self, manifest_body: dict) -> tuple[dict[str, Node], dict[str, dict]]:
        nodes: dict[str, Node] = {}
        metas: dict[str, dict] = {}
        for nid, entry in manifest_body["nodes"].items():
            if (type(entry) is not dict or set(entry) != {"active_revision", "tenant", "state"}
                    or type(entry["active_revision"]) is not int or entry["active_revision"] < 1
                    or type(entry["tenant"]) is not str or not entry["tenant"]
                    or type(entry["state"]) is not str or entry["state"] not in ("active", "tombstoned")):
                raise ValueError("INTEGRITY_FAILURE: manifest node entry")
            rev = entry["active_revision"]
            mp = self._meta_path(nid, rev)
            mdp = self._md_path(nid, rev)
            if not mp.exists() or not mdp.exists():
                raise ValueError("INTEGRITY_FAILURE: missing truth revision for " + nid)
            meta = self._read_meta_verified(mp)
            raw_md = mdp.read_bytes()
            if (_sha_bytes(raw_md) != meta["content_sha"] or meta["node_id"] != nid
                    or meta["revision"] != rev or meta["tenant"] != entry["tenant"]
                    or meta["state"] != entry["state"]):
                raise ValueError("INTEGRITY_FAILURE: meta/manifest mismatch for " + nid)
            edges = tuple(Edge(e["node_id"], e["relation"], e["revision"], e["content_sha"]) for e in meta["source_edges"])
            nodes[nid] = Node(
                meta["tenant"], rev, meta["content_sha"], meta["declared_sensitivity"],
                frozenset(meta["creation_readers"]), frozenset(meta["current_readers"]),
                edges, meta["state"] == "tombstoned",
            )
            metas[nid] = meta
        return nodes, metas

    def _rebuild_index_locked(self, manifest_body: dict, *, durable: bool, fault_hook=None) -> dict:
        _, metas = self._build_graph_nodes(manifest_body)
        inverted: dict[str, list[str]] = {}
        for nid in sorted(metas):
            body_text = self._md_path(nid, metas[nid]["revision"]).read_text(encoding="utf-8")
            for tok in wordset(body_text + " " + nid):
                inverted.setdefault(tok, []).append(nid)
        for tok in inverted:
            inverted[tok].sort()
        idx_body = {
            "schema_version": 1,
            "content_generation": manifest_body["content_generation"],
            "policy_generation": manifest_body["policy_generation"],
            "manifest_sha": _sha_obj(manifest_body),
            "inverted": inverted,
        }
        idx_body["index_sha"] = _sha_obj(idx_body)
        self._write_json_atomic(self._index_path(), idx_body, durable=durable, fault_hook=fault_hook, stage="index")
        return idx_body

    def rebuild_index(self, *, durable: bool = False) -> dict:
        """Rebuild the derived JSON inverted index strictly from immutable MD + meta truth."""
        with self._lock():
            self._recover_pending_transactions()
            manifest_body = self._load_manifest_or_init()
            return self._rebuild_index_locked(manifest_body, durable=durable)

    def _load_valid_index(self, manifest_body: dict) -> dict | None:
        ip = self._index_path()
        if not ip.exists():
            return None
        try:
            idx = self._read_json_strict(ip)
            expected = {"schema_version", "content_generation", "policy_generation", "manifest_sha", "inverted", "index_sha"}
            if type(idx) is not dict or set(idx) != expected:
                return None
            body = {k: v for k, v in idx.items() if k != "index_sha"}
            if _sha_obj(body) != idx["index_sha"]:
                return None
            if idx["manifest_sha"] != _sha_obj(manifest_body):
                return None
            if idx["content_generation"] != manifest_body["content_generation"] or idx["policy_generation"] != manifest_body["policy_generation"]:
                return None
            return idx
        except Exception:
            return None

    def recover_token_state(self, *, tenant: str, principal: str, operation: str, caller_token: str) -> dict:
        """Strictly recover historical state for a token scope without ever fabricating absent on empty disk."""
        with self._lock():
            self._recover_pending_transactions()
            return self.recover_token_state_unlocked(
                tenant=tenant, principal=principal, operation=operation, caller_token=caller_token,
            )

    def execute(self, request: dict, context: dict, now: int, *, request_id: str = "req-1",
                fault_hook=None, current_context_provider=None, current_now_provider=None) -> dict:
        if type(request) is dict and request.get("kind") == "Read.get":
            return self._read_get(request, context, now, request_id, current_context_provider, current_now_provider)
        req = validate_v2_request(request)
        try:
            ctx = context_shape(context)
            if type(now) is not int or not 0 <= now < ctx["expires_at"]:
                raise ValueError("AUTH_REQUIRED")
        except ValueError:
            scope = "read" if req["kind"].startswith("Read.") and req["kind"] != "Read.receipt" else ("receipt" if req["kind"] == "Read.receipt" else ("cancel" if req["kind"] == "Operation.cancel" else ("selfcheck" if req["kind"] == "SelfCheck" else "mutation")))
            return validate_full_response({
                "version": "0.2-full", "request_id": request_id, "scope": scope, "outcome": "error",
                "error_code": "AUTH_REQUIRED", "next_action": "authenticate",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })

        kind = req["kind"]
        with self._lock():
            self._recover_pending_transactions()
            if kind in ("Write.create", "Write.modify"):
                return self._write_locked(req, ctx, now, request_id, fault_hook=fault_hook)
            if kind == "Operation.cancel":
                return self._cancel_locked(req, ctx, now, request_id, fault_hook=fault_hook)
            if kind == "Read.receipt":
                return self._receipt_locked(req, ctx, request_id)
            if kind.startswith("Govern."):
                return self._govern_locked(req, ctx, now, request_id, fault_hook=fault_hook)
            if kind == "SelfCheck":
                return self._selfcheck_locked(req, request_id)
            return self._read_locked(
                req, ctx, now, request_id,
                current_context_provider=current_context_provider,
                current_now_provider=current_now_provider,
            )

    def _write_locked(self, req: dict, ctx: dict, now: int, rid: str, *, fault_hook=None) -> dict:
        kind = req["kind"]
        fp = request_fingerprint(req)
        tok_rec, tok_corrupt = self._load_token_record(ctx["tenant"], ctx["principal"], kind, req["caller_token"])
        if tok_corrupt:
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "unknown",
                "error_code": "INTEGRITY_FAILURE", "next_action": "query_same_token",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
                "historical_receipt": None, "selfcheck_aggregate": None,
            })

        manifest_body = self._load_manifest_or_init()
        if tok_rec is None:
            intent_rec, intent_corrupt = self._load_intent_for_scope(ctx["tenant"], ctx["principal"], kind, req["caller_token"])
            if intent_corrupt:
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "unknown",
                    "error_code": "INTEGRITY_FAILURE", "next_action": "query_same_token",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
                    "historical_receipt": None, "selfcheck_aggregate": None,
                })
            if intent_rec is not None:
                if intent_rec["fingerprint"] != fp:
                    return validate_full_response({
                        "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                        "error_code": "TOKEN_PAYLOAD_CONFLICT", "next_action": "fix_input",
                        "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                        "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                    })
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "unknown",
                    "error_code": "RECOVERY_UNCERTAIN", "next_action": "query_same_token",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
                    "historical_receipt": None, "selfcheck_aggregate": None,
                })
        if tok_rec is not None:
            same_fp = True if (tok_rec["fingerprint"] is None and tok_rec.get("negative_basis") == "durable_cancel") else (tok_rec["fingerprint"] == fp)
            action = retry_action(tok_rec["commit_status"], same_fp, tok_rec["history_complete"], tok_rec["negative_basis"])
            if action == "conflict":
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "TOKEN_PAYLOAD_CONFLICT", "next_action": "fix_input",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            if action == "return_original":
                nid = tok_rec["node_id"]
                nodes, metas = self._build_graph_nodes(manifest_body)
                can_r = can_read_with_epoch_cache(self.model, nid, nodes, tenant=ctx["tenant"], principal=ctx["principal"], clearance=ctx["clearance"], graph_epoch=manifest_body["graph_epoch"], cache=self.cache)
                proj = metas[nid]["state"] if can_r else "unknown"
                audit_norm = self._audit_status_norm(ctx["tenant"], tok_rec["receipt"])
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "ok" if audit_norm == "ok" else "error",
                    "error_code": None if audit_norm == "ok" else ("AUDIT_INCOMPLETE" if audit_norm == "missing" else "AUDIT_FAILED"),
                    "next_action": "return_original" if audit_norm == "ok" else "reconcile_audit",
                    "snapshot_ref": None, "policy_generation": manifest_body["policy_generation"], "records": None, "next_cursor": None,
                    "target": {"commit_status": "committed", "audit": audit_norm, "projection": proj, "negative_basis": "unassessed"},
                    "historical_receipt": copy.deepcopy(tok_rec["receipt"]), "selfcheck_aggregate": None,
                })
            if action == "return_original_cancel":
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "CANCELLED", "next_action": "return_original_cancel",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": {"commit_status": "absent", "audit": "unknown", "projection": "unknown", "negative_basis": "durable_cancel"},
                    "historical_receipt": None, "selfcheck_aggregate": None,
                })
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "unknown",
                "error_code": "RECOVERY_UNCERTAIN", "next_action": "query_same_token",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
                "historical_receipt": None, "selfcheck_aggregate": None,
            })

        durable = req["durability_request"] == "power"
        if durable:
            probe = self._probe_power()
            if not probe.get("supported"):
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "POWER_UNSUPPORTED", "next_action": "fix_input",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })

        readers = frozenset(req["reader_ceiling"])
        if ctx["principal"] not in readers or ctx["clearance"] < req["declared_sensitivity"]:
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                "error_code": "NOT_FOUND_OR_DENIED", "next_action": "authenticate",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })

        nodes, metas = self._build_graph_nodes(manifest_body)
        if kind == "Write.create":
            new_seq = manifest_body["node_seq"] + 1
            node_id = f"node-{new_seq}"
            rev = 1
            creation_readers = readers
        else:
            node_id = req["node_id"]
            if node_id not in metas or metas[node_id]["tenant"] != ctx["tenant"]:
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "NOT_FOUND_OR_DENIED", "next_action": "authenticate",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            cur_meta = metas[node_id]
            if not can_read_with_epoch_cache(self.model, node_id, nodes, tenant=ctx["tenant"], principal=ctx["principal"], clearance=ctx["clearance"], graph_epoch=manifest_body["graph_epoch"], cache=self.cache):
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "NOT_FOUND_OR_DENIED", "next_action": "authenticate",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            if cur_meta["revision"] != req["expected_revision"]:
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "REVISION_CONFLICT", "next_action": "refresh_snapshot",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            if cur_meta["state"] != "active":
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "STATE_CONFLICT", "next_action": "refresh_snapshot",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            if req["declared_sensitivity"] < cur_meta["declared_sensitivity"] or not readers <= frozenset(cur_meta["creation_readers"]):
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "POLICY_WIDENING_UNSUPPORTED", "next_action": "fix_input",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            new_seq = manifest_body["node_seq"]
            rev = cur_meta["revision"] + 1
            creation_readers = frozenset(cur_meta["creation_readers"])

        body_bytes = req["content"].encode("utf-8")
        content_sha = _sha_bytes(body_bytes)
        edges = tuple(Edge(e["node_id"], e["relation"], e["revision"], e["content_sha"]) for e in req["source_edges"])
        if edges:
            cand = dict(nodes)
            cand[node_id] = Node(ctx["tenant"], rev, content_sha, req["declared_sensitivity"], creation_readers, readers, edges, False)
            if self.model.decision(node_id, cand).quarantined:
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "INVALID_ARGUMENT", "next_action": "fix_input",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })

        # Refuse to overwrite an existing immutable revision MD file
        md_target = self._md_path(node_id, rev)
        meta_target = self._meta_path(node_id, rev)
        if md_target.exists() or meta_target.exists():
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "unknown",
                "error_code": "INTEGRITY_FAILURE", "next_action": "query_same_token",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
                "historical_receipt": None, "selfcheck_aggregate": None,
            })

        cond = extract_condition_space(req["condition_space"])
        bitemp = time_bundle(req["bitemporal"])
        meta_after = _seal_meta({
            "node_id": node_id, "revision": rev, "tenant": ctx["tenant"], "content_sha": content_sha,
            "declared_sensitivity": req["declared_sensitivity"], "creation_readers": sorted(creation_readers),
            "current_readers": sorted(readers), "source_edges": copy.deepcopy(req["source_edges"]),
            "condition_space": cond, "bitemporal": bitemp,
            "source_attribution": copy.deepcopy(req["source_attribution"]), "state": "active",
        })
        before_manifest = copy.deepcopy(manifest_body)
        after_manifest = copy.deepcopy(manifest_body)
        if kind == "Write.create":
            after_manifest["node_seq"] = new_seq
        after_manifest["content_generation"] += 1
        after_manifest["graph_epoch"] += 1
        after_manifest["nodes"][node_id] = {"active_revision": rev, "tenant": ctx["tenant"], "state": "active"}
        receipt = {"writer_id": self._writer_id, "commit_status": "committed", "fingerprint": fp,
                   "node_id": node_id, "revision": rev, "content_sha": content_sha,
                   "durability_actual": "power" if durable else "process", "audit_state": "missing"}
        intent = self._prepare_transaction(
            req=req, ctx=ctx, now=now, fp=fp, before_manifest=before_manifest,
            after_manifest=after_manifest,
            meta_changes=[{"revision": rev, "before": None, "after": meta_after}],
            new_md={"revision": rev, "content_sha": content_sha}, receipt=receipt,
            durable=durable, fault_hook=fault_hook,
        )
        receipt, audit_ok = self._run_prepared_transaction(intent, {"revision": rev, "content": req["content"]}, fault_hook=fault_hook)
        return validate_full_response({
            "version": "0.2-full", "request_id": rid, "scope": "mutation",
            "outcome": "ok" if audit_ok else "error", "error_code": None if audit_ok else "AUDIT_FAILED",
            "next_action": "return_original" if audit_ok else "reconcile_audit",
            "snapshot_ref": None, "policy_generation": after_manifest["policy_generation"],
            "records": None, "next_cursor": None,
            "target": {"commit_status": "committed", "audit": "ok" if audit_ok else "failed", "projection": "active", "negative_basis": "unassessed"},
            "historical_receipt": receipt, "selfcheck_aggregate": None,
        })

    def _cancel_locked(self, req: dict, ctx: dict, now: int, rid: str, *, fault_hook=None) -> dict:
        tok_rec, tok_corrupt = self._load_token_record(ctx["tenant"], ctx["principal"], req["target_operation"], req["caller_token"])
        if tok_corrupt:
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "cancel", "outcome": "unknown",
                "error_code": "INTEGRITY_FAILURE", "next_action": "query_same_token",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
                "historical_receipt": None, "selfcheck_aggregate": None,
            })
        manifest_body = self._load_manifest_or_init()
        if tok_rec is None:
            intent_rec, intent_corrupt = self._load_intent_for_scope(ctx["tenant"], ctx["principal"], req["target_operation"], req["caller_token"])
            if intent_corrupt:
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "cancel", "outcome": "unknown",
                    "error_code": "INTEGRITY_FAILURE", "next_action": "query_same_token",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
                    "historical_receipt": None, "selfcheck_aggregate": None,
                })
            if intent_rec is not None:
                nid, rev = intent_rec["node_id"], intent_rec["revision"]
                if self._md_path(nid, rev).exists() or self._meta_path(nid, rev).exists():
                    return validate_full_response({
                        "version": "0.2-full", "request_id": rid, "scope": "cancel", "outcome": "unknown",
                        "error_code": "RECOVERY_UNCERTAIN", "next_action": "query_same_token",
                        "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                        "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
                        "historical_receipt": None, "selfcheck_aggregate": None,
                    })
            # Sealing durable_cancel requires verified platform durability (never claim durable absent with durable=False)
            probe = self._probe_power()
            if not probe.get("supported"):
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "cancel", "outcome": "error",
                    "error_code": "POWER_UNSUPPORTED", "next_action": "query_same_token",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            basis = absence_basis(True, True, False, True, False)
            self._save_token_record(
                ctx["tenant"], ctx["principal"], req["target_operation"], req["caller_token"],
                {
                    "commit_status": "absent", "fingerprint": None, "history_complete": True,
                    "negative_basis": basis, "fencing_epoch": req["fencing_epoch"],
                    "node_id": None, "revision": None, "content_sha": None, "receipt": None,
                },
                durable=True, fault_hook=fault_hook,
            )
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "cancel", "outcome": "error",
                "error_code": "CANCELLED", "next_action": "return_original_cancel",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": {"commit_status": "absent", "audit": "unknown", "projection": "unknown", "negative_basis": basis},
                "historical_receipt": None, "selfcheck_aggregate": None,
            })
        if tok_rec["commit_status"] == "committed":
            nid = tok_rec["node_id"]
            nodes, metas = self._build_graph_nodes(manifest_body)
            can_r = can_read_with_epoch_cache(self.model, nid, nodes, tenant=ctx["tenant"], principal=ctx["principal"], clearance=ctx["clearance"], graph_epoch=manifest_body["graph_epoch"], cache=self.cache)
            proj = metas[nid]["state"] if can_r else "unknown"
            audit_norm = self._audit_status_norm(ctx["tenant"], tok_rec["receipt"])
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "cancel",
                "outcome": "ok" if audit_norm == "ok" else "error",
                "error_code": None if audit_norm == "ok" else ("AUDIT_INCOMPLETE" if audit_norm == "missing" else "AUDIT_FAILED"),
                "next_action": "return_original" if audit_norm == "ok" else "reconcile_audit",
                "snapshot_ref": None, "policy_generation": manifest_body["policy_generation"], "records": None, "next_cursor": None,
                "target": {"commit_status": "committed", "audit": audit_norm, "projection": proj, "negative_basis": "unassessed"},
                "historical_receipt": copy.deepcopy(tok_rec["receipt"]), "selfcheck_aggregate": None,
            })
        if tok_rec.get("negative_basis") == "durable_cancel":
            if req["fencing_epoch"] < tok_rec.get("fencing_epoch", 0):
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "cancel", "outcome": "error",
                    "error_code": "STATE_CONFLICT", "next_action": "return_original_cancel",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": {"commit_status": "absent", "audit": "unknown", "projection": "unknown", "negative_basis": "durable_cancel"},
                    "historical_receipt": None, "selfcheck_aggregate": None,
                })
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "cancel", "outcome": "error",
                "error_code": "CANCELLED", "next_action": "return_original_cancel",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": {"commit_status": "absent", "audit": "unknown", "projection": "unknown", "negative_basis": "durable_cancel"},
                "historical_receipt": None, "selfcheck_aggregate": None,
            })
        return validate_full_response({
            "version": "0.2-full", "request_id": rid, "scope": "cancel", "outcome": "unknown",
            "error_code": "RECOVERY_UNCERTAIN", "next_action": "query_same_token",
            "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
            "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
            "historical_receipt": None, "selfcheck_aggregate": None,
        })

    def _receipt_locked(self, req: dict, ctx: dict, rid: str) -> dict:
        tok_key = (ctx["tenant"], ctx["principal"], req["operation"], req["caller_token"])
        if not receipt_scope_allowed({"tenant": ctx["tenant"], "principal": ctx["principal"]}, tok_key, req["operation"], req["caller_token"]):
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "receipt", "outcome": "error",
                "error_code": "NOT_FOUND_OR_DENIED", "next_action": "authenticate",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })
        rec_state = self.recover_token_state_unlocked(tenant=ctx["tenant"], principal=ctx["principal"], operation=req["operation"], caller_token=req["caller_token"])
        tok_rec, _ = self._load_token_record(ctx["tenant"], ctx["principal"], req["operation"], req["caller_token"])
        if rec_state["integrity_failure"]:
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "receipt", "outcome": "unknown",
                "error_code": "INTEGRITY_FAILURE", "next_action": "query_same_token",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
                "historical_receipt": None, "selfcheck_aggregate": None,
            })
        if rec_state["commit_status"] == "unknown":
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "receipt", "outcome": "unknown",
                "error_code": "RECOVERY_UNCERTAIN", "next_action": "query_same_token",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
                "historical_receipt": None, "selfcheck_aggregate": None,
            })
        if rec_state["commit_status"] == "absent":
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "receipt", "outcome": "error",
                "error_code": "CANCELLED", "next_action": "return_original_cancel",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": {"commit_status": "absent", "audit": "unknown", "projection": "unknown", "negative_basis": "durable_cancel"},
                "historical_receipt": None, "selfcheck_aggregate": None,
            })
        manifest_body = self._load_manifest_or_init()
        nodes, metas = self._build_graph_nodes(manifest_body)
        nid = tok_rec["node_id"]
        can_r = can_read_with_epoch_cache(self.model, nid, nodes, tenant=ctx["tenant"], principal=ctx["principal"], clearance=ctx["clearance"], graph_epoch=manifest_body["graph_epoch"], cache=self.cache)
        proj = metas[nid]["state"] if can_r else "unknown"
        audit_st = rec_state["audit_state"]
        return validate_full_response({
            "version": "0.2-full", "request_id": rid, "scope": "receipt",
            "outcome": "ok" if audit_st == "ok" else "error",
            "error_code": None if audit_st == "ok" else ("AUDIT_INCOMPLETE" if audit_st == "missing" else "AUDIT_FAILED"),
            "next_action": "return_original" if audit_st == "ok" else "reconcile_audit",
            "snapshot_ref": None, "policy_generation": manifest_body["policy_generation"], "records": None, "next_cursor": None,
            "target": {"commit_status": "committed", "audit": audit_st, "projection": proj, "negative_basis": "unassessed"},
            "historical_receipt": copy.deepcopy(tok_rec["receipt"]), "selfcheck_aggregate": None,
        })

    def recover_token_state_unlocked(self, *, tenant: str, principal: str, operation: str, caller_token: str) -> dict:
        tok_rec, tok_corrupt = self._load_token_record(tenant, principal, operation, caller_token)
        if tok_corrupt:
            return {"commit_status": "unknown", "audit_state": "failed", "integrity_failure": True}
        audit_info = inspect_audit(self.root / "audit/audit.jsonl", expected_tenant=tenant)
        audit_ok = audit_info["state"] == "ok"
        audit_missing = audit_info["state"] == "missing"
        audit_state = "ok" if audit_ok else ("missing" if audit_missing else "failed")
        if tok_rec is None:
            return {"commit_status": "unknown", "audit_state": audit_state, "integrity_failure": audit_info["state"] in ("degraded", "integrity_failure")}
        if tok_rec["commit_status"] == "absent":
            basis = tok_rec["negative_basis"]
            if basis == "durable_cancel":
                return {"commit_status": "absent", "audit_state": "unknown", "integrity_failure": False, "negative_basis": "durable_cancel"}
            return {"commit_status": "unknown", "audit_state": "failed", "integrity_failure": True}
        if tok_rec["commit_status"] == "committed":
            audit_state = self._transaction_audit(audit_state, tok_rec["receipt"]["audit_state"])
            nid, rev = tok_rec["node_id"], tok_rec["revision"]
            mdp, metap = self._md_path(nid, rev), self._meta_path(nid, rev)
            body_ok = mdp.exists() and metap.exists()
            matching = True
            if body_ok:
                try:
                    meta = self._read_meta_verified(metap)
                    if (_sha_bytes(mdp.read_bytes()) != tok_rec["content_sha"]
                            or meta["content_sha"] != tok_rec["content_sha"]
                            or meta["node_id"] != nid or meta["revision"] != rev):
                        matching = False
                    entry = self._load_manifest_or_init()["nodes"].get(nid)
                    if (type(entry) is not dict or type(entry.get("active_revision")) is not int
                            or entry.get("tenant") != meta["tenant"]
                            or entry["active_revision"] < rev
                            or (entry["active_revision"] == rev and entry.get("state") != meta["state"])):
                        matching = False
                except Exception:
                    matching = False
            if not matching:
                return {"commit_status": "unknown", "audit_state": audit_state, "integrity_failure": True}
            if not body_ok:
                return {"commit_status": "unknown", "audit_state": audit_state, "integrity_failure": False}
            return {"commit_status": "committed", "audit_state": audit_state, "integrity_failure": audit_info["state"] in ("degraded", "integrity_failure")}
        return {"commit_status": "unknown", "audit_state": audit_state, "integrity_failure": False}

    def verify_record(self, *, node_id: str, expected_revision: int, verifier_id: str,
                      scope: str, method_allowed: bool, credential_exists: bool,
                      credential_time: int, verified_at: int) -> bool:
        with self._lock():
            self._recover_pending_transactions()
            entry = self._load_manifest_or_init()["nodes"].get(node_id)
            if entry is None or entry["active_revision"] != expected_revision:
                return False
            metap = self._meta_path(node_id, expected_revision)
            if not metap.exists():
                raise ValueError("INTEGRITY_FAILURE: missing verification subject metadata")
            meta = self._read_meta_verified(metap)
            mdp = self._md_path(node_id, expected_revision)
            if (meta["node_id"] != node_id or meta["revision"] != expected_revision
                    or meta["tenant"] != entry["tenant"] or meta["state"] != entry["state"]
                    or not mdp.exists() or _sha_bytes(mdp.read_bytes()) != meta["content_sha"]):
                raise ValueError("INTEGRITY_FAILURE: verification subject mismatch")
            source_id = meta["source_attribution"]["source_id"]
            ok = verification_eligible(
                subject_revision=meta["revision"],
                subject_sha=meta["content_sha"],
                proof_revision=expected_revision,
                proof_sha=meta["content_sha"],
                verifier_id=verifier_id,
                source_id=source_id,
                scope_covers=scope in ("full", "restore"),
                method_allowed=method_allowed,
                credential_exists=credential_exists,
                credential_time=credential_time,
                verified_at=verified_at,
            )
            if ok:
                vp = self.root / "verifications" / f"{_node_dir_key(node_id)}_rev_{expected_revision:06d}.json"
                proof_body = {
                    "node_id": node_id,
                    "subject_revision": meta["revision"],
                    "subject_sha": meta["content_sha"],
                    "verifier_id": verifier_id,
                    "source_id": source_id,
                    "scope": scope,
                    "method_allowed": bool(method_allowed),
                    "credential_exists": bool(credential_exists),
                    "credential_time": credential_time,
                    "verified_at": verified_at,
                }
                proof_body["proof_sha"] = _sha_obj(proof_body)
                self._write_json_atomic(vp, proof_body, durable=False)
            return ok

    def _is_verified_locked(self, node_id: str, rev: int, content_sha: str, source_id: str, required_scope: str = "restore") -> bool:
        vp = self.root / "verifications" / f"{_node_dir_key(node_id)}_rev_{rev:06d}.json"
        if not vp.exists():
            return False
        try:
            proof = self._read_json_strict(vp)
            expected = {"node_id", "subject_revision", "subject_sha", "verifier_id", "source_id", "scope", "method_allowed", "credential_exists", "credential_time", "verified_at", "proof_sha"}
            if type(proof) is not dict or set(proof) != expected:
                return False
            body = {k: v for k, v in proof.items() if k != "proof_sha"}
            if _sha_obj(body) != proof["proof_sha"]:
                return False
            if proof["node_id"] != node_id or proof["source_id"] != source_id:
                return False
            return verification_eligible(
                subject_revision=rev,
                subject_sha=content_sha,
                proof_revision=proof["subject_revision"],
                proof_sha=proof["subject_sha"],
                verifier_id=proof["verifier_id"],
                source_id=source_id,
                scope_covers=proof["scope"] in ("full", required_scope),
                method_allowed=proof["method_allowed"],
                credential_exists=proof["credential_exists"],
                credential_time=proof["credential_time"],
                verified_at=proof["verified_at"],
            )
        except Exception:
            return False

    def _govern_locked(self, req: dict, ctx: dict, now: int, rid: str, *, fault_hook=None) -> dict:
        kind = req["kind"]
        action = kind.split(".", 1)[1]
        node_id = req["node_id"]
        fp = request_fingerprint(req)
        tok_rec, tok_corrupt = self._load_token_record(ctx["tenant"], ctx["principal"], kind, req["caller_token"])
        if tok_corrupt:
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "unknown",
                "error_code": "INTEGRITY_FAILURE", "next_action": "query_same_token",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
                "historical_receipt": None, "selfcheck_aggregate": None,
            })
        manifest_body = self._load_manifest_or_init()
        nodes, metas = self._build_graph_nodes(manifest_body)
        if tok_rec is not None:
            if tok_rec["fingerprint"] != fp:
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "TOKEN_PAYLOAD_CONFLICT", "next_action": "fix_input",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            if tok_rec["commit_status"] != "committed":
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "unknown",
                    "error_code": "RECOVERY_UNCERTAIN", "next_action": "query_same_token",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
                    "historical_receipt": None, "selfcheck_aggregate": None,
                })
            can_r = can_read_with_epoch_cache(self.model, node_id, nodes, tenant=ctx["tenant"], principal=ctx["principal"], clearance=ctx["clearance"], graph_epoch=manifest_body["graph_epoch"], cache=self.cache)
            proj = metas[node_id]["state"] if can_r else "unknown"
            audit_norm = self._audit_status_norm(ctx["tenant"], tok_rec["receipt"])
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "mutation",
                "outcome": "ok" if audit_norm == "ok" else "error",
                "error_code": None if audit_norm == "ok" else ("AUDIT_INCOMPLETE" if audit_norm == "missing" else "AUDIT_FAILED"),
                "next_action": "return_original" if audit_norm == "ok" else "reconcile_audit",
                "snapshot_ref": None, "policy_generation": manifest_body["policy_generation"], "records": None, "next_cursor": None,
                "target": {"commit_status": "committed", "audit": audit_norm, "projection": proj, "negative_basis": "unassessed"},
                "historical_receipt": copy.deepcopy(tok_rec["receipt"]), "selfcheck_aggregate": None,
            })

        intent_rec, intent_corrupt = self._load_intent_for_scope(ctx["tenant"], ctx["principal"], kind, req["caller_token"])
        if intent_corrupt:
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "unknown",
                "error_code": "INTEGRITY_FAILURE", "next_action": "query_same_token",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
                "historical_receipt": None, "selfcheck_aggregate": None,
            })
        if intent_rec is not None:
            conflict = intent_rec.get("fingerprint") != fp
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "mutation",
                "outcome": "error" if conflict else "unknown",
                "error_code": "TOKEN_PAYLOAD_CONFLICT" if conflict else "RECOVERY_UNCERTAIN",
                "next_action": "fix_input" if conflict else "query_same_token",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None if conflict else {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
                "historical_receipt": None, "selfcheck_aggregate": None,
            })
        cur_meta = metas.get(node_id)
        authorized = cur_meta is not None and cur_meta["tenant"] == ctx["tenant"] and ctx["principal"] in cur_meta["creation_readers"] and ctx["clearance"] >= cur_meta["declared_sensitivity"]
        if not authorized:
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                "error_code": "NOT_FOUND_OR_DENIED", "next_action": "authenticate",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })

        policy_safe = True
        if action == "change_policy":
            policy_safe = req["declared_sensitivity"] >= cur_meta["declared_sensitivity"] and frozenset(req["reader_ceiling"]) <= frozenset(cur_meta["creation_readers"])
        elif action == "correct_revision":
            rep = req["replacement"]
            policy_safe = rep["declared_sensitivity"] >= cur_meta["declared_sensitivity"] and frozenset(rep["reader_ceiling"]) <= frozenset(cur_meta["creation_readers"])
        proof_fresh = self._is_verified_locked(node_id, cur_meta["revision"], cur_meta["content_sha"], cur_meta["source_attribution"]["source_id"], "restore") if action == "restore" else True

        try:
            govern_transition(cur_meta["state"], cur_meta["revision"], req["expected_revision"], action, authorized, policy_safe, proof_fresh)
        except ValueError as exc:
            code = str(exc)
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                "error_code": code, "next_action": "refresh_snapshot" if code in ("REVISION_CONFLICT", "STATE_CONFLICT") else "fix_input",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })

        before_manifest = copy.deepcopy(manifest_body)
        meta_changes = []
        new_md_content = None
        new_md = None
        if action in ("forget", "restore"):
            new_state = "tombstoned" if action == "forget" else "active"
            updated_meta = copy.deepcopy(cur_meta)
            updated_meta["state"] = new_state
            meta_changes.append({"revision": cur_meta["revision"], "before": copy.deepcopy(cur_meta), "after": _seal_meta(updated_meta)})
            manifest_body["content_generation"] += 1
            manifest_body["graph_epoch"] += 1
            manifest_body["nodes"][node_id]["state"] = new_state
            new_rev = cur_meta["revision"]
            sha = cur_meta["content_sha"]
            proj = new_state
        elif action == "change_policy":
            updated_meta = copy.deepcopy(cur_meta)
            updated_meta["declared_sensitivity"] = req["declared_sensitivity"]
            updated_meta["current_readers"] = sorted(set(req["reader_ceiling"]))
            meta_changes.append({"revision": cur_meta["revision"], "before": copy.deepcopy(cur_meta), "after": _seal_meta(updated_meta)})
            manifest_body["policy_generation"] += 1
            manifest_body["graph_epoch"] += 1
            new_rev = cur_meta["revision"]
            sha = cur_meta["content_sha"]
            proj = "active"
        else:  # correct_revision
            rep = req["replacement"]
            old_rev = cur_meta["revision"]
            new_rev = old_rev + 1
            sha = _sha_bytes(rep["content"].encode("utf-8"))
            edges = tuple(Edge(e["node_id"], e["relation"], e["revision"], e["content_sha"]) for e in rep["source_edges"])
            if edges:
                cand = dict(nodes)
                cand[node_id] = Node(ctx["tenant"], new_rev, sha, rep["declared_sensitivity"], frozenset(cur_meta["creation_readers"]), frozenset(rep["reader_ceiling"]), edges, False)
                if self.model.decision(node_id, cand).quarantined:
                    return validate_full_response({
                        "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                        "error_code": "INVALID_ARGUMENT", "next_action": "fix_input",
                        "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                        "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                    })
            if self._md_path(node_id, new_rev).exists() or self._meta_path(node_id, new_rev).exists():
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "unknown",
                    "error_code": "INTEGRITY_FAILURE", "next_action": "query_same_token",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
                    "historical_receipt": None, "selfcheck_aggregate": None,
                })
            cond = extract_condition_space(rep["condition_space"])
            bitemp = time_bundle(rep["bitemporal"])
            new_meta = _seal_meta({
                "node_id": node_id, "revision": new_rev, "tenant": ctx["tenant"], "content_sha": sha,
                "declared_sensitivity": rep["declared_sensitivity"], "creation_readers": list(cur_meta["creation_readers"]),
                "current_readers": sorted(set(rep["reader_ceiling"])), "source_edges": copy.deepcopy(rep["source_edges"]),
                "condition_space": cond, "bitemporal": bitemp, "source_attribution": copy.deepcopy(rep["source_attribution"]),
                "state": "active",
            })
            old_meta = copy.deepcopy(cur_meta)
            old_meta["state"] = "superseded"
            meta_changes.extend([
                {"revision": new_rev, "before": None, "after": new_meta},
                {"revision": old_rev, "before": copy.deepcopy(cur_meta), "after": _seal_meta(old_meta)},
            ])
            new_md = {"revision": new_rev, "content_sha": sha}
            new_md_content = {"revision": new_rev, "content": rep["content"]}
            manifest_body["content_generation"] += 1
            manifest_body["graph_epoch"] += 1
            manifest_body["nodes"][node_id]["active_revision"] = new_rev
            manifest_body["nodes"][node_id]["state"] = "active"
            proj = "active"

        receipt = {
            "writer_id": self._writer_id,
            "commit_status": "committed", "fingerprint": fp, "node_id": node_id,
            "revision": new_rev, "content_sha": sha, "durability_actual": "process", "audit_state": "missing",
        }
        intent = self._prepare_transaction(
            req=req, ctx=ctx, now=now, fp=fp, before_manifest=before_manifest,
            after_manifest=manifest_body, meta_changes=meta_changes, new_md=new_md,
            receipt=receipt, durable=False, fault_hook=fault_hook,
        )
        receipt, audit_ok = self._run_prepared_transaction(intent, new_md_content, fault_hook=fault_hook)
        return validate_full_response({
            "version": "0.2-full", "request_id": rid, "scope": "mutation",
            "outcome": "ok" if audit_ok else "error", "error_code": None if audit_ok else "AUDIT_FAILED",
            "next_action": "return_original" if audit_ok else "reconcile_audit",
            "snapshot_ref": None, "policy_generation": manifest_body["policy_generation"],
            "records": None, "next_cursor": None,
            "target": {"commit_status": "committed", "audit": "ok" if audit_ok else "failed", "projection": proj, "negative_basis": "unassessed"},
            "historical_receipt": receipt, "selfcheck_aggregate": None,
        })

    def _selfcheck_locked(self, req: dict, rid: str) -> dict:
        from framework.api import aggregate_checks
        checks = [{"id": cid, "status": "NOT_RUN"} for cid in req["check_ids"]]
        agg = aggregate_checks(req["check_ids"], checks)
        manifest_body = self._load_manifest_or_init()
        return validate_full_response({
            "version": "0.2-full", "request_id": rid, "scope": "selfcheck",
            "outcome": "unknown",
            "error_code": "CONDITION_DEFERRED",
            "next_action": "refresh_snapshot",
            "snapshot_ref": req["snapshot_ref"], "policy_generation": manifest_body["policy_generation"],
            "records": None, "next_cursor": None, "target": None, "historical_receipt": None,
            "selfcheck_aggregate": agg,
        })

    def _read_get(self, request, context, now, request_id, current_context, current_now):
        with self._lock():
            recovered = False
            def snapshot():
                nonlocal recovered
                if not recovered:
                    self._recover_pending_transactions()
                    recovered = True
                manifest = self._load_manifest_or_init()
                nodes, metadata = self._build_graph_nodes(manifest)
                return ReadSnapshot(manifest['content_generation'], manifest['policy_generation'], nodes, metadata)

            return read_get(request, context=context, now=now, request_id=request_id,
                            snapshot=snapshot, model=self.model,
                            body=lambda key, rev: self._md_path(key, rev).read_bytes().decode('utf-8'),
                            current_context=current_context if current_context is not None else lambda: context,
                            current_now=current_now if current_now is not None else lambda: now)

    def _search_candidates(self, req, ctx, now, manifest, nodes, metas, offset):
        idx = self._load_valid_index(manifest)
        bodies = {}

        def ranking_body(key, revision):
            text = self._md_path(key, revision).read_bytes().decode("utf-8")
            bodies[key] = text
            return text

        view = ReadSnapshot(manifest["content_generation"], manifest["policy_generation"], nodes, metas)
        page = read_search(req, context=ctx, now=now, view=view, postings=None if idx is None else idx["inverted"],
                           body=ranking_body, model=self.model, offset=offset)
        return page, bodies

    def _read_locked(self, req: dict, ctx: dict, now: int, rid: str, *,
                     current_context_provider=None, current_now_provider=None) -> dict:
        manifest_body = self._load_manifest_or_init()
        if ctx["policy_generation"] != manifest_body["policy_generation"]:
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "read", "outcome": "error",
                "error_code": "POLICY_CHANGED", "next_action": "refresh_snapshot",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })

        nodes, metas = self._build_graph_nodes(manifest_body)
        kind = req["kind"]
        cond_q = extract_condition_space(req["condition_query"])
        time_q = {req["time_axis"]: req["time_point"]}
        snap_id = f"snap-{manifest_body['content_generation']}-{manifest_body['policy_generation']}"
        query_params = {k: v for k, v in req.items() if k != "cursor"}
        q_sha = _sha_obj(query_params)
        cursor_sha = None

        if "cursor" in req:
            c_tok = req["cursor"]
            c_obj = self._cursors.get(c_tok)
            cursor_sha = hashlib.sha256(c_tok.encode("utf-8")).hexdigest()
            binding = {
                "tenant": ctx["tenant"], "principal": ctx["principal"], "read_kind": kind,
                "query_sha": q_sha, "snapshot": snap_id, "policy_generation": manifest_body["policy_generation"],
            }
            if not cursor_valid(c_obj, binding, now):
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "read", "outcome": "error",
                    "error_code": "POLICY_CHANGED", "next_action": "refresh_snapshot",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            offset = self._cursor_offsets.get(c_tok, 0)
        else:
            offset = 0

        def _can_read(nid: str, c_ctx: dict) -> bool:
            return can_read_with_epoch_cache(
                self.model, nid, nodes, tenant=c_ctx["tenant"], principal=c_ctx["principal"],
                clearance=c_ctx["clearance"], graph_epoch=manifest_body["graph_epoch"], cache=self.cache,
            )

        if kind == "Read.search":
            page, bodies = self._search_candidates(req, ctx, now, manifest_body, nodes, metas, offset)
            if page.error is not None:
                action = "fix_input" if page.error == "CONDITION_DEFERRED" else "refresh_snapshot"
                return validate_full_response(dict(version="0.2-full", request_id=rid, scope="read", outcome="error",
                    error_code=page.error, next_action=action, snapshot_ref=None, policy_generation=None, records=None,
                    next_cursor=None, target=None, historical_receipt=None, selfcheck_aggregate=None))
            page_ids = [locator["id"] for locator in page.locators]
            has_more, limit = page.has_more, req["limit"]
        else:
            root_id = req["node_id"]
            if not _can_read(root_id, ctx):
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "read", "outcome": "error",
                    "error_code": "NOT_FOUND_OR_DENIED", "next_action": "authenticate",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            frontier = {root_id}
            collected = []
            for _ in range(req["depth"]):
                nxt = set()
                for cur_id in sorted(frontier):
                    for e in nodes[cur_id].edges:
                        if _can_read(e.target, ctx) and e.target not in collected:
                            collected.append(e.target)
                            nxt.add(e.target)
                frontier = nxt
            authorized_ids = collected
            limit = req["limit"]

            matched_ids = []
            saw_defer = False
            bodies: dict[str, str] = {}
            for nid in authorized_ids:
                meta = metas[nid]
                cv = condition_match(meta["condition_space"], cond_q)
                tv = bitemporal_match(meta["bitemporal"], time_q)
                if cv == "NO_MATCH" or tv == "NO_MATCH":
                    continue
                if cv == "DEFER" or tv == "DEFER":
                    saw_defer = True
                    continue
                matched_ids.append(nid)
                bodies[nid] = self._md_path(nid, meta["revision"]).read_text(encoding="utf-8")

            if saw_defer:
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "read", "outcome": "error",
                    "error_code": "CONDITION_DEFERRED", "next_action": "fix_input",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })

            page_ids = matched_ids[offset:offset + limit]
            has_more = offset + limit < len(matched_ids)

        out_records = []
        for nid in page_ids:
            meta = metas[nid]
            loc = {"id": nid, "revision": meta["revision"], "content_sha": meta["content_sha"]}
            prov = None
            if req["include_provenance"]:
                redacted = sum(1 for e in nodes[nid].edges if not _can_read(e.target, ctx))
                prov = {
                    "source_kind": meta["source_attribution"]["source_kind"],
                    "source_id": meta["source_attribution"]["source_id"],
                    "redacted_edges": redacted,
                }
            out_records.append(build_untrusted_record(loc, bodies[nid], prov))

        next_cursor_tok = None
        if has_more and kind in ("Read.search", "Read.expand"):
            c_obj = {
                "tenant": ctx["tenant"], "principal": ctx["principal"], "read_kind": kind,
                "query_sha": q_sha, "snapshot": snap_id, "policy_generation": manifest_body["policy_generation"],
                "expires_at": ctx["expires_at"],
            }
            next_cursor_tok = "cur-" + _sha_obj(dict(c_obj, offset=offset + limit))[:24]
            self._cursors[next_cursor_tok] = dict(c_obj)
            self._cursor_offsets[next_cursor_tok] = offset + limit

        prelim = {
            "version": "0.2-full", "request_id": rid, "scope": "read", "outcome": "ok",
            "error_code": None, "next_action": "none",
            "snapshot_ref": snap_id, "policy_generation": manifest_body["policy_generation"],
            "records": out_records, "next_cursor": next_cursor_tok,
            "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
        }
        resp_sha = _sha_obj(prelim)
        prepared_binding = binding_shape({
            "context": copy.deepcopy(ctx),
            "snapshot": {"id": snap_id, "content_generation": manifest_body["content_generation"], "policy_generation": manifest_body["policy_generation"], "expires_at": ctx["expires_at"]},
            "read_kind": kind, "query_sha": q_sha, "response_sha": resp_sha, "cursor_sha": cursor_sha,
        })
        live_manifest = self._load_manifest_or_init()
        live_nodes, _ = self._build_graph_nodes(live_manifest)
        live_ctx = context_shape(current_context_provider() if current_context_provider is not None else ctx)
        live_now = current_now_provider() if current_now_provider is not None else now
        live_binding = binding_shape({
            "context": live_ctx,
            "snapshot": {"id": f"snap-{live_manifest['content_generation']}-{live_manifest['policy_generation']}", "content_generation": live_manifest["content_generation"], "policy_generation": live_manifest["policy_generation"], "expires_at": live_ctx["expires_at"]},
            "read_kind": kind, "query_sha": q_sha, "response_sha": resp_sha, "cursor_sha": cursor_sha,
        })
        reauth_ok = all(
            can_read_with_epoch_cache(
                self.model, rec["locator"]["id"], live_nodes, tenant=live_ctx["tenant"],
                principal=live_ctx["principal"], clearance=live_ctx["clearance"],
                graph_epoch=live_manifest["graph_epoch"], cache=self.cache,
            )
            for rec in out_records
        )
        if not emit_allowed(prepared_binding, live_binding, live_now, True, reauth_ok, True):
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "read", "outcome": "error",
                "error_code": "POLICY_CHANGED", "next_action": "refresh_snapshot",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })
        return validate_full_response(prelim)
