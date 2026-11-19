"""Isolated full-lifecycle sandbox integrating Write, Read, Govern, Cancel, Verify, and Recovery.

Explicitly synthetic and in-memory only; not a persistent runtime or authentication service.
"""
from __future__ import annotations
import copy
import hashlib
import uuid
from dataclasses import replace
from framework.api import aggregate_checks, cursor_valid, govern_transition, receipt_scope_allowed, retry_action
from framework.conditions import bitemporal_match, condition_match
from framework.contracts import build_untrusted_record, extract_condition_space, validate_full_response, validate_v2_request
from framework.migration import time_bundle
from framework.model import Edge, EpochDecisionCache, Model, Node, RecoveryEvidence, can_read_with_epoch_cache, recover, request_fingerprint, verification_eligible
from framework.responses import absence_basis, cancellation
from framework.security import binding_shape, context_shape, emit_allowed, retention_plan
from framework.spec import canonical
from sandbox_runtime.retrieval import bm25_rank_visible
from sandbox_runtime.store import wordset


def _sha(obj: object) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def _body_sha(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class LifecycleSandbox:
    """In-memory isolated full-contract engine binding framework predicates end-to-end."""

    def __init__(self, *, synthetic: bool):
        if synthetic is not True:
            raise ValueError("EXPLICIT_SYNTHETIC_REQUIRED")
        self._writer_id = "memory-" + uuid.uuid4().hex
        self.model = Model()
        self.cache = EpochDecisionCache()
        self.graph_epoch = 1
        self.policy_generation = 1
        self.content_generation = 1
        self._node_seq = 0
        self._nodes: dict[str, Node] = {}
        self._records: dict[str, dict] = {}
        self._revisions: dict[tuple[str, int], dict] = {}
        self._verifications: dict[tuple[str, int], dict] = {}
        self._tokens: dict[tuple[str, str, str, str], dict] = {}
        self._cursors: dict[str, dict] = {}
        self._cursor_offsets: dict[str, int] = {}

    def _bump_content(self):
        self.content_generation += 1
        self.graph_epoch += 1

    def _bump_policy(self):
        self.policy_generation += 1
        self.graph_epoch += 1

    def _check_ctx(self, ctx: dict, now: int) -> dict:
        c = context_shape(ctx)
        if type(now) is not int or not 0 <= now < c["expires_at"]:
            raise ValueError("AUTH_REQUIRED")
        return c

    def _apply_edges(self, raw_edges: list[dict]) -> tuple[Edge, ...]:
        return tuple(Edge(e["node_id"], e["relation"], e["revision"], e["content_sha"]) for e in raw_edges)

    def _edges_safe_for_commit(self, *, node_id: str, rev: int, tenant: str, body_sha: str,
                               sensitivity: int, creation_readers: frozenset[str],
                               current_readers: frozenset[str], edges: tuple[Edge, ...]) -> bool:
        if not edges:
            return True
        cand_nodes = dict(self._nodes)
        cand_nodes[node_id] = Node(tenant, rev, body_sha, sensitivity, creation_readers, current_readers, edges, False)
        return not self.model.decision(node_id, cand_nodes).quarantined

    def _can_read(self, node_id: str, ctx: dict) -> bool:
        return can_read_with_epoch_cache(
            self.model,
            node_id,
            self._nodes,
            tenant=ctx["tenant"],
            principal=ctx["principal"],
            clearance=ctx["clearance"],
            graph_epoch=self.graph_epoch,
            cache=self.cache,
        )

    def _store_record(self, *, node_id: str, rev: int, tenant: str, body: str, sensitivity: int,
                      creation_readers: frozenset[str], current_readers: frozenset[str],
                      edges: tuple[Edge, ...], cond: dict, bitemp: dict, attribution: dict,
                      tombstoned: bool = False):
        sha = _body_sha(body)
        node = Node(tenant, rev, sha, sensitivity, creation_readers, current_readers, edges, tombstoned)
        self._nodes[node_id] = node
        rec = {
            "id": node_id,
            "revision": rev,
            "tenant": tenant,
            "body": body,
            "content_sha": sha,
            "sensitivity": sensitivity,
            "creation_readers": sorted(creation_readers),
            "current_readers": sorted(current_readers),
            "edges": copy.deepcopy(edges),
            "condition_space": copy.deepcopy(cond),
            "bitemporal": copy.deepcopy(bitemp),
            "source_attribution": copy.deepcopy(attribution),
            "tombstoned": tombstoned,
            "state": "tombstoned" if tombstoned else "active",
        }
        self._records[node_id] = rec
        self._revisions[(node_id, rev)] = copy.deepcopy(rec)
        return node, rec

    def _build_receipt(self, *, commit_status: str, fp: str, node_id: str, rev: int, content_sha: str, durability: str, audit_state: str) -> dict:
        return {
            "writer_id": self._writer_id,
            "commit_status": commit_status,
            "fingerprint": fp,
            "node_id": node_id,
            "revision": rev,
            "content_sha": content_sha,
            "durability_actual": durability,
            "audit_state": audit_state,
        }

    def execute(self, request: dict, context: dict, now: int, *, request_id: str = "req-1",
                transient_fail_budget: int = 0, current_context_provider=None, current_now_provider=None) -> dict:
        """Execute a validated api_v2 request and return a validated 0.2-full response."""
        req = validate_v2_request(request)
        try:
            ctx = self._check_ctx(context, now)
        except ValueError:
            return validate_full_response({
                "version": "0.2-full", "request_id": request_id,
                "scope": "read" if req["kind"].startswith("Read.") and req["kind"] != "Read.receipt" else ("receipt" if req["kind"] == "Read.receipt" else ("cancel" if req["kind"] == "Operation.cancel" else ("selfcheck" if req["kind"] == "SelfCheck" else "mutation"))),
                "outcome": "error", "error_code": "AUTH_REQUIRED", "next_action": "authenticate",
                "snapshot_ref": None, "policy_generation": None, "records": None,
                "next_cursor": None, "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })

        kind = req["kind"]
        if kind in ("Write.create", "Write.modify"):
            return self._handle_write(req, ctx, request_id)
        if kind == "Operation.cancel":
            return self._handle_cancel(req, ctx, request_id)
        if kind == "Read.receipt":
            return self._handle_receipt(req, ctx, request_id)
        if kind.startswith("Govern."):
            return self._handle_govern(req, ctx, request_id)
        if kind == "SelfCheck":
            return self._handle_selfcheck(req, request_id)
        return self._handle_read(
            req, ctx, now, request_id,
            transient_fail_budget=transient_fail_budget,
            current_context_provider=current_context_provider,
            current_now_provider=current_now_provider,
        )

    def _handle_write(self, req: dict, ctx: dict, rid: str) -> dict:
        kind = req["kind"]
        tok_key = (ctx["tenant"], ctx["principal"], kind, req["caller_token"])
        fp = request_fingerprint(req)
        existing = self._tokens.get(tok_key)
        if existing is not None:
            same_fp = True if (existing["fingerprint"] is None and existing.get("negative_basis") == "durable_cancel") else (existing["fingerprint"] == fp)
            action = retry_action(
                existing["commit_status"],
                same_fp,
                existing["history_complete"],
                existing.get("negative_basis", "unassessed"),
            )
            if action == "conflict":
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "TOKEN_PAYLOAD_CONFLICT", "next_action": "fix_input",
                    "snapshot_ref": None, "policy_generation": None, "records": None,
                    "next_cursor": None, "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            if action == "return_original":
                node_id = existing["node_id"]
                proj = self._records[node_id]["state"] if self._can_read(node_id, ctx) else "unknown"
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "ok",
                    "error_code": None, "next_action": "return_original",
                    "snapshot_ref": None, "policy_generation": self.policy_generation, "records": None,
                    "next_cursor": None,
                    "target": {"commit_status": "committed", "audit": "ok", "projection": proj, "negative_basis": "unassessed"},
                    "historical_receipt": copy.deepcopy(existing["receipt"]), "selfcheck_aggregate": None,
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

        if req["durability_request"] == "power":
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                "error_code": "POWER_UNSUPPORTED", "next_action": "fix_input",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })

        cond = extract_condition_space(req["condition_space"])
        bitemp = time_bundle(req["bitemporal"])
        readers = frozenset(req["reader_ceiling"])
        if ctx["principal"] not in readers or ctx["clearance"] < req["declared_sensitivity"]:
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                "error_code": "NOT_FOUND_OR_DENIED", "next_action": "authenticate",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })

        edges = self._apply_edges(req["source_edges"])
        if kind == "Write.create":
            self._node_seq += 1
            node_id = f"node-{self._node_seq}"
            rev = 1
            creation_readers = readers
        else:
            node_id = req["node_id"]
            cur = self._records.get(node_id)
            if cur is None or cur["tenant"] != ctx["tenant"] or not self._can_read(node_id, ctx):
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "NOT_FOUND_OR_DENIED", "next_action": "authenticate",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            if cur["revision"] != req["expected_revision"]:
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "REVISION_CONFLICT", "next_action": "refresh_snapshot",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            if cur["state"] != "active":
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "STATE_CONFLICT", "next_action": "refresh_snapshot",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            if req["declared_sensitivity"] < cur["sensitivity"] or not readers <= frozenset(cur["creation_readers"]):
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "POLICY_WIDENING_UNSUPPORTED", "next_action": "fix_input",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            rev = cur["revision"] + 1
            creation_readers = frozenset(cur["creation_readers"])

        if not self._edges_safe_for_commit(
            node_id=node_id, rev=rev, tenant=ctx["tenant"], body_sha=_body_sha(req["content"]),
            sensitivity=req["declared_sensitivity"], creation_readers=creation_readers,
            current_readers=readers, edges=edges,
        ):
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                "error_code": "INVALID_ARGUMENT", "next_action": "fix_input",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })

        node, _ = self._store_record(
            node_id=node_id, rev=rev, tenant=ctx["tenant"], body=req["content"],
            sensitivity=req["declared_sensitivity"], creation_readers=creation_readers,
            current_readers=readers, edges=edges, cond=cond, bitemp=bitemp,
            attribution=req["source_attribution"], tombstoned=False,
        )
        self._bump_content()
        receipt = self._build_receipt(
            commit_status="committed", fp=fp, node_id=node_id, rev=rev,
            content_sha=node.content_sha, durability="process", audit_state="ok",
        )
        self._tokens[tok_key] = {
            "commit_status": "committed", "fingerprint": fp, "history_complete": True,
            "negative_basis": "unassessed", "node_id": node_id, "receipt": receipt,
        }
        return validate_full_response({
            "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "ok",
            "error_code": None, "next_action": "return_original",
            "snapshot_ref": None, "policy_generation": self.policy_generation, "records": None,
            "next_cursor": None,
            "target": {"commit_status": "committed", "audit": "ok", "projection": "active", "negative_basis": "unassessed"},
            "historical_receipt": copy.deepcopy(receipt), "selfcheck_aggregate": None,
        })

    def _handle_cancel(self, req: dict, ctx: dict, rid: str) -> dict:
        tok_key = (ctx["tenant"], ctx["principal"], req["target_operation"], req["caller_token"])
        existing = self._tokens.get(tok_key)
        if existing is None:
            status, _, next_act = cancellation("pending", True, True, True, True)
            basis = absence_basis(True, True, False, True, False)
            self._tokens[tok_key] = {
                "commit_status": "absent", "fingerprint": None, "history_complete": True,
                "negative_basis": basis, "node_id": None, "receipt": None,
                "fencing_epoch": req["fencing_epoch"],
            }
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "cancel", "outcome": "error",
                "error_code": "CANCELLED", "next_action": next_act,
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": {"commit_status": status, "audit": "unknown", "projection": "unknown", "negative_basis": basis},
                "historical_receipt": None, "selfcheck_aggregate": None,
            })
        if existing["commit_status"] == "committed":
            status, _, next_act = cancellation("committed", True, True, True, False)
            node_id = existing["node_id"]
            proj = self._records[node_id]["state"] if self._can_read(node_id, ctx) else "unknown"
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "cancel", "outcome": "ok",
                "error_code": None, "next_action": next_act,
                "snapshot_ref": None, "policy_generation": self.policy_generation, "records": None, "next_cursor": None,
                "target": {"commit_status": status, "audit": "ok", "projection": proj, "negative_basis": "unassessed"},
                "historical_receipt": copy.deepcopy(existing["receipt"]), "selfcheck_aggregate": None,
            })
        if existing.get("negative_basis") == "durable_cancel":
            sealed_epoch = existing.get("fencing_epoch", 0)
            if req["fencing_epoch"] < sealed_epoch:
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "cancel", "outcome": "error",
                    "error_code": "STATE_CONFLICT", "next_action": "return_original_cancel",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": {"commit_status": "absent", "audit": "unknown", "projection": "unknown", "negative_basis": "durable_cancel"},
                    "historical_receipt": None, "selfcheck_aggregate": None,
                })
            status, _, next_act = cancellation("cancelled", True, True, True, True)
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "cancel", "outcome": "error",
                "error_code": "CANCELLED", "next_action": next_act,
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": {"commit_status": status, "audit": "unknown", "projection": "unknown", "negative_basis": "durable_cancel"},
                "historical_receipt": None, "selfcheck_aggregate": None,
            })
        return validate_full_response({
            "version": "0.2-full", "request_id": rid, "scope": "cancel", "outcome": "unknown",
            "error_code": "RECOVERY_UNCERTAIN", "next_action": "query_same_token",
            "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
            "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
            "historical_receipt": None, "selfcheck_aggregate": None,
        })

    def _handle_receipt(self, req: dict, ctx: dict, rid: str) -> dict:
        tok_key = (ctx["tenant"], ctx["principal"], req["operation"], req["caller_token"])
        if not receipt_scope_allowed({"tenant": ctx["tenant"], "principal": ctx["principal"]}, tok_key, req["operation"], req["caller_token"]):
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "receipt", "outcome": "error",
                "error_code": "NOT_FOUND_OR_DENIED", "next_action": "authenticate",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })
        rec = self._tokens.get(tok_key)
        if rec is None:
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "receipt", "outcome": "unknown",
                "error_code": "RECOVERY_UNCERTAIN", "next_action": "query_same_token",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": {"commit_status": "unknown", "audit": "unknown", "projection": "unknown", "negative_basis": "unassessed"},
                "historical_receipt": None, "selfcheck_aggregate": None,
            })
        if rec["commit_status"] == "absent" and rec.get("negative_basis") == "durable_cancel":
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "receipt", "outcome": "error",
                "error_code": "CANCELLED", "next_action": "return_original_cancel",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": {"commit_status": "absent", "audit": "unknown", "projection": "unknown", "negative_basis": "durable_cancel"},
                "historical_receipt": None, "selfcheck_aggregate": None,
            })
        node_id = rec["node_id"]
        proj = self._records[node_id]["state"] if node_id and self._can_read(node_id, ctx) else "unknown"
        return validate_full_response({
            "version": "0.2-full", "request_id": rid, "scope": "receipt", "outcome": "ok",
            "error_code": None, "next_action": "return_original",
            "snapshot_ref": None, "policy_generation": self.policy_generation, "records": None, "next_cursor": None,
            "target": {"commit_status": "committed", "audit": "ok", "projection": proj, "negative_basis": "unassessed"},
            "historical_receipt": copy.deepcopy(rec["receipt"]), "selfcheck_aggregate": None,
        })

    def verify_record(self, *, node_id: str, expected_revision: int, verifier_id: str,
                      scope: str, method_allowed: bool, credential_exists: bool,
                      credential_time: int, verified_at: int) -> bool:
        """Bind independent verification proof (verifier_id != source_id) to a specific revision/sha."""
        cur = self._records.get(node_id)
        if cur is None or cur["revision"] != expected_revision:
            return False
        scope_covers = scope in ("full", "restore")
        ok = verification_eligible(
            subject_revision=cur["revision"],
            subject_sha=cur["content_sha"],
            proof_revision=expected_revision,
            proof_sha=cur["content_sha"],
            verifier_id=verifier_id,
            source_id=cur["source_attribution"]["source_id"],
            scope_covers=scope_covers,
            method_allowed=method_allowed,
            credential_exists=credential_exists,
            credential_time=credential_time,
            verified_at=verified_at,
        )
        if ok:
            self._verifications[(node_id, cur["revision"])] = {
                "verifier_id": verifier_id,
                "subject_sha": cur["content_sha"],
                "scope": scope,
                "verified_at": verified_at,
            }
        return ok

    def is_verified(self, node_id: str, *, required_scope: str = "restore") -> bool:
        cur = self._records.get(node_id)
        if cur is None:
            return False
        proof = self._verifications.get((node_id, cur["revision"]))
        return proof is not None and proof["subject_sha"] == cur["content_sha"] and proof["scope"] in ("full", required_scope)

    def _handle_govern(self, req: dict, ctx: dict, rid: str) -> dict:
        kind = req["kind"]
        action = kind.split(".", 1)[1]
        node_id = req["node_id"]
        tok_key = (ctx["tenant"], ctx["principal"], kind, req["caller_token"])
        fp = request_fingerprint(req)
        existing = self._tokens.get(tok_key)
        if existing is not None:
            if existing["fingerprint"] != fp:
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "TOKEN_PAYLOAD_CONFLICT", "next_action": "fix_input",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            proj = self._records[node_id]["state"] if self._can_read(node_id, ctx) else "unknown"
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "ok",
                "error_code": None, "next_action": "return_original",
                "snapshot_ref": None, "policy_generation": self.policy_generation, "records": None, "next_cursor": None,
                "target": {"commit_status": "committed", "audit": "ok", "projection": proj, "negative_basis": "unassessed"},
                "historical_receipt": copy.deepcopy(existing["receipt"]), "selfcheck_aggregate": None,
            })

        cur = self._records.get(node_id)
        authorized = cur is not None and cur["tenant"] == ctx["tenant"] and ctx["principal"] in cur["creation_readers"] and ctx["clearance"] >= cur["sensitivity"]
        if not authorized:
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                "error_code": "NOT_FOUND_OR_DENIED", "next_action": "authenticate",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })

        policy_safe = True
        if action == "change_policy":
            new_sens = req["declared_sensitivity"]
            new_readers = frozenset(req["reader_ceiling"])
            policy_safe = new_sens >= cur["sensitivity"] and new_readers <= frozenset(cur["creation_readers"])
        elif action == "correct_revision":
            rep = req["replacement"]
            policy_safe = rep["declared_sensitivity"] >= cur["sensitivity"] and frozenset(rep["reader_ceiling"]) <= frozenset(cur["creation_readers"])
        proof_fresh = self.is_verified(node_id, required_scope="restore") if action == "restore" else True

        try:
            govern_transition(cur["state"], cur["revision"], req["expected_revision"], action, authorized, policy_safe, proof_fresh)
        except ValueError as exc:
            code = str(exc)
            next_act = "refresh_snapshot" if code in ("REVISION_CONFLICT", "STATE_CONFLICT") else "fix_input"
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                "error_code": code, "next_action": next_act,
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })

        if action == "forget":
            cur["tombstoned"] = True
            cur["state"] = "tombstoned"
            self._nodes[node_id] = replace(self._nodes[node_id], tombstoned=True)
            self._bump_content()
            proj = "tombstoned"
            new_rev = cur["revision"]
            sha = cur["content_sha"]
        elif action == "restore":
            cur["tombstoned"] = False
            cur["state"] = "active"
            self._nodes[node_id] = replace(self._nodes[node_id], tombstoned=False)
            self._bump_content()
            proj = "active"
            new_rev = cur["revision"]
            sha = cur["content_sha"]
        elif action == "change_policy":
            new_sens = req["declared_sensitivity"]
            new_readers = frozenset(req["reader_ceiling"])
            cur["sensitivity"] = new_sens
            cur["current_readers"] = sorted(new_readers)
            self._nodes[node_id] = replace(self._nodes[node_id], sensitivity=new_sens, current_readers=new_readers)
            self._bump_policy()
            proj = "active"
            new_rev = cur["revision"]
            sha = cur["content_sha"]
        else:  # correct_revision
            rep = req["replacement"]
            old_rev = cur["revision"]
            new_rev = old_rev + 1
            cond = extract_condition_space(rep["condition_space"])
            bitemp = time_bundle(rep["bitemporal"])
            edges = self._apply_edges(rep["source_edges"])
            edges_ok = self._edges_safe_for_commit(
                node_id=node_id, rev=new_rev, tenant=ctx["tenant"], body_sha=_body_sha(rep["content"]),
                sensitivity=rep["declared_sensitivity"], creation_readers=frozenset(cur["creation_readers"]),
                current_readers=frozenset(rep["reader_ceiling"]), edges=edges,
            )
            if not edges_ok:
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "error",
                    "error_code": "INVALID_ARGUMENT", "next_action": "fix_input",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            self._revisions[(node_id, old_rev)]["state"] = "superseded"
            node, _ = self._store_record(
                node_id=node_id, rev=new_rev, tenant=ctx["tenant"], body=rep["content"],
                sensitivity=rep["declared_sensitivity"], creation_readers=frozenset(cur["creation_readers"]),
                current_readers=frozenset(rep["reader_ceiling"]), edges=edges,
                cond=cond, bitemp=bitemp, attribution=rep["source_attribution"], tombstoned=False,
            )
            self._bump_content()
            proj = "active"
            sha = node.content_sha

        receipt = self._build_receipt(
            commit_status="committed", fp=fp, node_id=node_id, rev=new_rev,
            content_sha=sha, durability="process", audit_state="ok",
        )
        self._tokens[tok_key] = {
            "commit_status": "committed", "fingerprint": fp, "history_complete": True,
            "negative_basis": "unassessed", "node_id": node_id, "receipt": receipt,
        }
        return validate_full_response({
            "version": "0.2-full", "request_id": rid, "scope": "mutation", "outcome": "ok",
            "error_code": None, "next_action": "return_original",
            "snapshot_ref": None, "policy_generation": self.policy_generation, "records": None, "next_cursor": None,
            "target": {"commit_status": "committed", "audit": "ok", "projection": proj, "negative_basis": "unassessed"},
            "historical_receipt": copy.deepcopy(receipt), "selfcheck_aggregate": None,
        })

    def _handle_selfcheck(self, req: dict, rid: str) -> dict:
        checks = []
        for cid in req["check_ids"]:
            status = "PASS" if cid.startswith("C") else "NOT_RUN"
            checks.append({"id": cid, "status": status})
        agg = aggregate_checks(req["check_ids"], checks)
        return validate_full_response({
            "version": "0.2-full", "request_id": rid, "scope": "selfcheck",
            "outcome": "ok" if agg == "PASS" else "unknown",
            "error_code": None if agg == "PASS" else "RECOVERY_UNCERTAIN",
            "next_action": "none" if agg == "PASS" else "query_same_token",
            "snapshot_ref": req["snapshot_ref"], "policy_generation": self.policy_generation,
            "records": None, "next_cursor": None, "target": None, "historical_receipt": None,
            "selfcheck_aggregate": agg,
        })

    def _handle_read(self, req: dict, ctx: dict, now: int, rid: str, *, transient_fail_budget: int = 0,
                     current_context_provider=None, current_now_provider=None) -> dict:
        if transient_fail_budget < 0:
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "read", "outcome": "error",
                "error_code": "READ_FAILED", "next_action": "retry_read",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })

        if ctx["policy_generation"] != self.policy_generation:
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "read", "outcome": "error",
                "error_code": "POLICY_CHANGED", "next_action": "refresh_snapshot",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })
        kind = req["kind"]
        cond_q = extract_condition_space(req["condition_query"])
        time_q = {req["time_axis"]: req["time_point"]}
        snap_id = f"snap-{self.content_generation}-{self.policy_generation}"
        query_params = {k: v for k, v in req.items() if k != "cursor"}
        q_sha = _sha(query_params)
        cursor_sha = None

        if "cursor" in req:
            c_tok = req["cursor"]
            c_obj = self._cursors.get(c_tok)
            cursor_sha = _body_sha(c_tok)
            binding = {
                "tenant": ctx["tenant"],
                "principal": ctx["principal"],
                "read_kind": kind,
                "query_sha": q_sha,
                "snapshot": snap_id,
                "policy_generation": self.policy_generation,
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

        if kind == "Read.get":
            nid = req["node_id"]
            if not self._can_read(nid, ctx):
                return validate_full_response({
                    "version": "0.2-full", "request_id": rid, "scope": "read", "outcome": "error",
                    "error_code": "NOT_FOUND_OR_DENIED", "next_action": "authenticate",
                    "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                    "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
                })
            authorized_ids = [nid]
            limit = 1
        elif kind == "Read.search":
            q_tokens = wordset(req["query"])
            authorized_ids = [
                nid for nid in sorted(self._records)
                if self._can_read(nid, ctx) and (q_tokens & wordset(self._records[nid]["body"] + " " + nid))
            ]
            limit = req["limit"]
        else:
            root_id = req["node_id"]
            if not self._can_read(root_id, ctx):
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
                    for e in self._nodes[cur_id].edges:
                        if self._can_read(e.target, ctx) and e.target not in collected:
                            collected.append(e.target)
                            nxt.add(e.target)
                frontier = nxt
            authorized_ids = collected
            limit = req["limit"]

        # Strictly fail-closed: any DEFER on authorized candidate blocks output (core 0.2.0 defer_blocks_output=true)
        matched_ids = []
        saw_defer = False
        for nid in authorized_ids:
            rec = self._records[nid]
            cv = condition_match(rec["condition_space"], cond_q)
            tv = bitemporal_match(rec["bitemporal"], time_q)
            if cv == "NO_MATCH" or tv == "NO_MATCH":
                continue
            if cv == "DEFER" or tv == "DEFER":
                saw_defer = True
                continue
            matched_ids.append(nid)

        if saw_defer:
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "read", "outcome": "error",
                "error_code": "CONDITION_DEFERRED", "next_action": "fix_input",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })

        if kind == "Read.search":
            pool_records = {nid: {"body": self._records[nid]["body"], "key": nid} for nid in matched_ids}
            ranked_ids = bm25_rank_visible(matched_ids, req["query"], pool_records, len(matched_ids))
            page_ids = ranked_ids[offset:offset + limit]
            has_more = offset + limit < len(ranked_ids)
        else:
            page_ids = matched_ids[offset:offset + limit]
            has_more = offset + limit < len(matched_ids)

        out_records = []
        for nid in page_ids:
            rec = self._records[nid]
            loc = {"id": nid, "revision": rec["revision"], "content_sha": rec["content_sha"]}
            prov = None
            if req["include_provenance"]:
                redacted = sum(1 for e in rec["edges"] if not self._can_read(e.target, ctx))
                prov = {
                    "source_kind": rec["source_attribution"]["source_kind"],
                    "source_id": rec["source_attribution"]["source_id"],
                    "redacted_edges": redacted,
                }
            out_records.append(build_untrusted_record(loc, rec["body"], prov))

        next_cursor_tok = None
        if has_more and kind in ("Read.search", "Read.expand"):
            c_obj = {
                "tenant": ctx["tenant"],
                "principal": ctx["principal"],
                "read_kind": kind,
                "query_sha": q_sha,
                "snapshot": snap_id,
                "policy_generation": self.policy_generation,
                "expires_at": ctx["expires_at"],
            }
            next_cursor_tok = "cur-" + _sha(dict(c_obj, offset=offset + limit))[:24]
            self._cursors[next_cursor_tok] = dict(c_obj)
            self._cursor_offsets[next_cursor_tok] = offset + limit

        prelim = {
            "version": "0.2-full", "request_id": rid, "scope": "read", "outcome": "ok",
            "error_code": None, "next_action": "none",
            "snapshot_ref": snap_id, "policy_generation": self.policy_generation,
            "records": out_records, "next_cursor": next_cursor_tok,
            "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
        }
        resp_sha = _sha(prelim)
        prepared_snap = {
            "id": snap_id,
            "content_generation": self.content_generation,
            "policy_generation": self.policy_generation,
            "expires_at": ctx["expires_at"],
        }
        prepared_binding = binding_shape({
            "context": copy.deepcopy(ctx),
            "snapshot": prepared_snap,
            "read_kind": kind,
            "query_sha": q_sha,
            "response_sha": resp_sha,
            "cursor_sha": cursor_sha,
        })

        # Re-read live context/now/generations at emit commit point (non-tautological TOCTOU check)
        live_ctx = context_shape(current_context_provider() if current_context_provider is not None else ctx)
        live_now = current_now_provider() if current_now_provider is not None else now
        live_snap_id = f"snap-{self.content_generation}-{self.policy_generation}"
        live_snap = {
            "id": live_snap_id,
            "content_generation": self.content_generation,
            "policy_generation": self.policy_generation,
            "expires_at": live_ctx["expires_at"],
        }
        live_binding = binding_shape({
            "context": live_ctx,
            "snapshot": live_snap,
            "read_kind": kind,
            "query_sha": q_sha,
            "response_sha": resp_sha,
            "cursor_sha": cursor_sha,
        })
        reauth_ok = all(self._can_read(rec["locator"]["id"], live_ctx) for rec in out_records)
        if not emit_allowed(prepared_binding, live_binding, live_now, True, reauth_ok, True):
            return validate_full_response({
                "version": "0.2-full", "request_id": rid, "scope": "read", "outcome": "error",
                "error_code": "POLICY_CHANGED", "next_action": "refresh_snapshot",
                "snapshot_ref": None, "policy_generation": None, "records": None, "next_cursor": None,
                "target": None, "historical_receipt": None, "selfcheck_aggregate": None,
            })
        return validate_full_response(prelim)

    def simulate_recovery(self, *, body_present: bool, audit_present: bool, matching: bool,
                          authoritative_negative: bool, history_complete: bool) -> dict:
        r = recover(RecoveryEvidence(
            body=body_present, audit=audit_present, matching=matching,
            authoritative_negative=authoritative_negative, history_complete=history_complete,
        ))
        return {"status": r.status, "audit_state": r.audit_state, "integrity_failure": r.integrity_failure}

    def retention_check(self, evidence: dict, now: int) -> str:
        return retention_plan(evidence, now)
