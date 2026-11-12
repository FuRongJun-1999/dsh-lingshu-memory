"""Small pure reference model. It does not store files or authenticate users."""
from __future__ import annotations
from dataclasses import dataclass
import copy
import hashlib
from .spec import load, validate, canonical

@dataclass(frozen=True)
class Edge:
    target: str
    relation: str
    revision: int
    content_sha: str

@dataclass(frozen=True)
class Node:
    tenant: str
    revision: int
    content_sha: str
    sensitivity: int
    creation_readers: frozenset[str]
    current_readers: frozenset[str]
    edges: tuple[Edge, ...] = ()
    tombstoned: bool = False

@dataclass(frozen=True)
class Decision:
    sensitivity: int
    readers: frozenset[str]
    quarantined: bool
    notes: tuple[str, ...]

class Model:
    def __init__(self, spec=None):
        self.spec = copy.deepcopy(validate(spec if spec is not None else load()))

    def formation(self, edges):
        if any(e.relation not in self.spec["edges"]["relations"] for e in edges):
            raise ValueError("invalid relation")
        rule = self.spec["formation"]
        return rule["true_result"] if any(e.relation == rule["relation"] for e in edges) else rule["false_result"]

    def decision(self, node_id, nodes):
        maximum = self.spec["sensitivity"]["max"]
        relations = self.spec["edges"]["relations"]
        memo = {}
        def closed(reason):
            return Decision(maximum, frozenset(), True, (reason,))
        def walk(key, stack):
            if key in stack:
                return closed("cycle")
            if key in memo:
                return memo[key]
            n = nodes.get(key)
            if n is None or n.tombstoned:
                return closed("missing_or_tombstoned")
            if type(n.sensitivity) is not int or n.sensitivity not in self.spec["sensitivity"]["levels"]:
                return closed("invalid_sensitivity")
            if type(n.revision) is not int or n.revision < 1 or not n.tenant or not n.content_sha:
                return closed("invalid_revision")
            sensitivity = n.sensitivity
            readers = n.creation_readers & n.current_readers
            quarantine = False
            notes = []
            for e in n.edges:
                if e.relation not in relations:
                    return closed("invalid_relation")
                target = nodes.get(e.target)
                # Validate EVERY edge before skipping independent evidence.
                if target is None or target.tombstoned:
                    sensitivity = maximum
                    notes.append("dangling")
                    quarantine = True
                    continue
                if target.tenant != n.tenant:
                    return closed("cross_tenant")
                if type(e.revision) is not int or e.revision != target.revision or e.content_sha != target.content_sha:
                    return closed("source_revision_mismatch")
                if e.relation == "unknown":
                    sensitivity = maximum
                    notes.append("unknown_relation")
                elif e.relation == self.spec["sensitivity"]["inherit_relation"]:
                    sub = walk(e.target, stack | {key})
                    sensitivity = max(sensitivity, sub.sensitivity)
                    readers &= sub.readers
                    quarantine |= sub.quarantined
                    notes.extend(sub.notes)
            result = Decision(sensitivity, frozenset() if quarantine else readers, quarantine, tuple(sorted(set(notes))))
            memo[key] = result
            return result
        # All source relations must be acyclic; only derived inherits labels.
        visited, active = set(), set()
        def acyclic(key):
            if key in active: return False
            if key in visited or key not in nodes: return True
            active.add(key)
            for source in nodes[key].edges:
                if not acyclic(source.target): return False
            active.remove(key)
            visited.add(key)
            return True
        if not acyclic(node_id): return closed("cycle")
        return walk(node_id, set())

    def can_read(self, node_id, nodes, *, tenant, principal, clearance):
        n = nodes.get(node_id)
        if n is None or n.tenant != tenant or type(clearance) is not int or clearance not in self.spec["sensitivity"]["levels"]:
            return False
        d = self.decision(node_id, nodes)
        return not d.quarantined and principal in d.readers and clearance >= d.sensitivity

    def append_allowed(self, node_id, edge, nodes):
        # A pre-commit check only. Persisted revisions remain immutable.
        from dataclasses import replace
        if node_id not in nodes or edge.target not in nodes or edge.relation not in self.spec["edges"]["relations"]:
            return False
        owner, target = nodes[node_id], nodes[edge.target]
        if owner.tenant != target.tenant or target.tombstoned:
            return False
        if edge.revision != target.revision or edge.content_sha != target.content_sha:
            return False
        candidate = dict(nodes)
        candidate[node_id] = replace(owner, edges=owner.edges + (edge,))
        return not self.decision(node_id, candidate).quarantined

    def retract(self, *_args, **_kwargs):
        raise ValueError("immutable revision; create a correction revision")

@dataclass(frozen=True)
class RecoveryEvidence:
    body: bool = False
    audit: bool = False
    matching: bool = True
    authoritative_negative: bool = False
    history_complete: bool = False

@dataclass(frozen=True)
class RecoveryResult:
    status: str
    audit_state: str
    integrity_failure: bool


def recover(evidence):
    # Inputs are assumed authenticated evidence, not user-supplied proof flags.
    e = evidence
    if any(type(getattr(e, name)) is not bool for name in ("body", "audit", "matching", "authoritative_negative", "history_complete")):
        raise ValueError("invalid recovery evidence type")
    if not e.matching or (e.authoritative_negative and (e.body or e.audit)):
        return RecoveryResult("unknown", "failed", True)
    if e.body:
        return RecoveryResult("committed", "ok" if e.audit else "missing", False)
    if e.audit:
        return RecoveryResult("unknown", "ok", False)
    if e.authoritative_negative and e.history_complete:
        return RecoveryResult("absent", "missing", False)
    return RecoveryResult("unknown", "missing", False)


def request_fingerprint(request):
    def check(value):
        if value is None or type(value) in (str, bool, int):
            return
        if type(value) is list:
            for item in value: check(item)
            return
        if type(value) is dict and all(type(key) is str for key in value):
            for item in value.values(): check(item)
            return
        raise ValueError("request must use integer-only JSON with string keys")
    if type(request) is not dict:
        raise ValueError("request must be a JSON object")
    check(request)
    return hashlib.sha256(canonical(request)).hexdigest()

class TokenHistory:
    """Sequential toy history. Never use it as a production transaction store."""
    def __init__(self):
        self.history = {}
        self.projection = {}
    def submit(self, *, tenant, principal, operation, token, request, history_complete=True):
        if not all(type(x) is str and x for x in (tenant, principal, operation, token)):
            raise ValueError("missing token scope")
        key = (tenant, principal, operation, token)
        fingerprint = request_fingerprint(request)
        old = self.history.get(key)
        if old is not None:
            if old[0] != fingerprint:
                raise ValueError("token_payload_conflict")
            return old[1]
        if not history_complete:
            raise ValueError("unknown_block_retry")
        receipt = ("committed", len(self.history) + 1, fingerprint)
        self.history[key] = (fingerprint, receipt)
        self.projection[key] = "active"
        return receipt
    def forget(self, *, tenant, principal, operation, token):
        key = (tenant, principal, operation, token)
        if key not in self.history:
            raise ValueError("unknown_token")
        self.projection[key] = "tombstoned"
    def current(self, *, tenant, principal, operation, token):
        return self.projection.get((tenant, principal, operation, token), "unknown")


def verification_eligible(*, subject_revision, subject_sha, proof_revision, proof_sha,
                          verifier_id, source_id, scope_covers, method_allowed,
                          credential_exists, credential_time, verified_at):
    # Time values here are comparable integer instants in one trusted time domain.
    return (type(subject_revision) is int and subject_revision > 0
            and type(proof_revision) is int and subject_revision == proof_revision
            and type(subject_sha) is str and type(proof_sha) is str and bool(subject_sha) and subject_sha == proof_sha
            and type(verifier_id) is str and type(source_id) is str
            and bool(verifier_id) and bool(source_id) and verifier_id != source_id
            and scope_covers is True and method_allowed is True and credential_exists is True
            and type(credential_time) is int and type(verified_at) is int
            and credential_time < verified_at)
