"""Independent expected values; do not derive expectations from the model."""
import copy
import unittest
from dataclasses import replace
from framework.model import (Model, Node, Edge, RecoveryEvidence, recover,
                             TokenHistory, request_fingerprint, verification_eligible)
from framework.spec import load, validate, parse, digest
from scripts.spec_tools import freeze_errors

READERS = frozenset({"alice", "bob"})
def node(name, sensitivity=0, **patch):
    return replace(Node("tenant-a", 1, "hash-" + name, sensitivity, READERS, READERS), **patch)
def edge(name, relation="derived", **patch):
    return replace(Edge(name, relation, 1, "hash-" + name), **patch)

class GraphTests(unittest.TestCase):
    def setUp(self):
        self.m = Model()
    def test_formation_empty_and_mixed(self):
        self.assertEqual(self.m.formation(()), "direct")
        self.assertEqual(self.m.formation((edge("a"), edge("b", "corroborating"))), "derived")
        self.assertEqual(self.m.formation((edge("a", "unknown"),)), "direct")
    def test_dangling_all_four_relations(self):
        for relation in ("derived", "corroborating", "contradicting", "unknown"):
            with self.subTest(relation=relation):
                d = self.m.decision("n", {"n": node("n", edges=(edge("ghost", relation),))})
                self.assertEqual(d.sensitivity, 3)
                self.assertIn("dangling", d.notes)
    def test_dangling_independent_then_derived_downstream(self):
        for relation in ("corroborating", "contradicting"):
            nodes = {"a": node("a", edges=(edge("ghost", relation),)), "b": node("b", edges=(edge("a"),))}
            self.assertEqual(self.m.decision("b", nodes).sensitivity, 3)
    def test_resolved_independent_not_inherited(self):
        for relation in ("corroborating", "contradicting"):
            nodes = {"a": node("a", 3), "b": node("b", edges=(edge("a", relation),))}
            self.assertEqual(self.m.decision("b", nodes).sensitivity, 0)
    def test_unknown_resolved_is_max(self):
        nodes = {"a": node("a"), "b": node("b", edges=(edge("a", "unknown"),))}
        self.assertEqual(self.m.decision("b", nodes).sensitivity, 3)
    def test_clearance_direction(self):
        nodes = {"a": node("a", 2)}
        self.assertFalse(self.m.can_read("a", nodes, tenant="tenant-a", principal="alice", clearance=1))
        self.assertTrue(self.m.can_read("a", nodes, tenant="tenant-a", principal="alice", clearance=3))
    def test_invalid_clearance_and_sensitivity(self):
        for bad in (True, -1, 4, "3"):
            with self.subTest(bad=bad):
                self.assertFalse(self.m.can_read("a", {"a": node("a")}, tenant="tenant-a", principal="alice", clearance=bad))
                self.assertTrue(self.m.decision("a", {"a": node("a", bad)}).quarantined)
    def test_cross_tenant_every_relation(self):
        for relation in ("derived", "corroborating", "contradicting", "unknown"):
            nodes = {"a": node("a", tenant="tenant-b"), "b": node("b", edges=(edge("a", relation),))}
            self.assertTrue(self.m.decision("b", nodes).quarantined)
    def test_reader_intersection_and_tightening(self):
        nodes = {"a": node("a", current_readers=frozenset({"alice"})), "b": node("b", edges=(edge("a"),))}
        self.assertEqual(self.m.decision("b", nodes).readers, frozenset({"alice"}))
        self.assertFalse(self.m.can_read("b", nodes, tenant="tenant-a", principal="bob", clearance=3))
    def test_source_widen_does_not_expand_creation(self):
        nodes = {"a": node("a", creation_readers=frozenset({"alice"})), "b": node("b", edges=(edge("a"),))}
        self.assertEqual(self.m.decision("b", nodes).readers, frozenset({"alice"}))
    def test_revision_and_hash_mismatch(self):
        for changed in (replace(edge("a"), revision=2), replace(edge("a"), content_sha="wrong")):
            nodes = {"a": node("a"), "b": node("b", edges=(changed,))}
            d = self.m.decision("b", nodes)
            self.assertTrue(d.quarantined)
            self.assertEqual(d.sensitivity, 3)
    def test_tombstoned_source_is_unresolvable(self):
        for relation in ("derived", "corroborating"):
            nodes = {"a": node("a", tombstoned=True), "b": node("b", edges=(edge("a", relation),))}
            self.assertEqual(self.m.decision("b", nodes).sensitivity, 3)
    def test_three_level_cycle_and_diamond(self):
        cycle = {"a": node("a", edges=(edge("b"),)), "b": node("b", edges=(edge("c"),)), "c": node("c", edges=(edge("a"),))}
        self.assertTrue(self.m.decision("a", cycle).quarantined)
        diamond = {"a": node("a", edges=(edge("b"), edge("c"))), "b": node("b", edges=(edge("d"),)), "c": node("c", edges=(edge("d"),)), "d": node("d", 2)}
        self.assertFalse(self.m.decision("a", diamond).quarantined)
        self.assertEqual(self.m.decision("a", diamond).sensitivity, 2)
    def test_append_cycle_rejected(self):
        nodes = {"a": node("a"), "b": node("b", edges=(edge("c"),)), "c": node("c", edges=(edge("a"),))}
        self.assertFalse(self.m.append_allowed("a", edge("b"), nodes))
    def test_retract_refused(self):
        for relation in ("derived", "corroborating", "unknown"):
            with self.assertRaises(ValueError):
                self.m.retract(edge("a", relation))

class BoundaryTests(unittest.TestCase):
    def test_nested_bool_not_integer_level(self):
        s = load();s["sensitivity"]["levels"][0] = False
        with self.assertRaises(ValueError): validate(s)
    def test_spec_snapshot_is_detached(self):
        s = load();m = Model(s);s["formation"]["relation"] = "unknown"
        self.assertEqual(m.formation((edge("a"),)), "derived")
    def test_missing_derived_source_cannot_grant_max_reader(self):
        m = Model();nodes = {"n": node("n", edges=(edge("ghost"),))}
        self.assertFalse(m.can_read("n", nodes, tenant="tenant-a", principal="alice", clearance=3))
    def test_boolean_edge_revision_quarantines(self):
        m = Model();nodes = {"a": node("a"), "b": node("b", edges=(edge("a", revision=True),))}
        self.assertTrue(m.decision("b", nodes).quarantined)
    def test_recovery_non_boolean_evidence_rejected(self):
        with self.assertRaises(ValueError): recover(RecoveryEvidence(body="false"))

class RecoveryTests(unittest.TestCase):
    def test_all_presence_states(self):
        expected = {(True, True): "committed", (True, False): "committed", (False, True): "unknown", (False, False): "unknown"}
        for state, status in expected.items():
            with self.subTest(state=state):
                self.assertEqual(recover(RecoveryEvidence(body=state[0], audit=state[1])).status, status)
    def test_negative_evidence_not_scan_absence(self):
        self.assertEqual(recover(RecoveryEvidence(history_complete=True)).status, "unknown")
        self.assertEqual(recover(RecoveryEvidence(authoritative_negative=True)).status, "unknown")
        self.assertEqual(recover(RecoveryEvidence(authoritative_negative=True, history_complete=True)).status, "absent")
    def test_conflicts_never_commit(self):
        for e in (RecoveryEvidence(body=True, matching=False), RecoveryEvidence(body=True, authoritative_negative=True)):
            result = recover(e)
            self.assertEqual(result.status, "unknown")
            self.assertTrue(result.integrity_failure)
    def test_missing_audit_reported(self):
        self.assertEqual(recover(RecoveryEvidence(body=True)).audit_state, "missing")

class TokenTests(unittest.TestCase):
    def setUp(self):
        self.h = TokenHistory()
        self.scope = dict(tenant="tenant-a", principal="alice", operation="write", token="request-one")
    def test_repeat_returns_original(self):
        first = self.h.submit(**self.scope, request={"content": "x", "sensitivity": 1})
        self.assertEqual(first, self.h.submit(**self.scope, request={"sensitivity": 1, "content": "x"}))
        self.assertEqual(len(self.h.history), 1)
    def test_full_semantics_fingerprint(self):
        self.h.submit(**self.scope, request={"content": "x", "sensitivity": 1})
        with self.assertRaises(ValueError):
            self.h.submit(**self.scope, request={"content": "x", "sensitivity": 2})
    def test_forget_does_not_release_token(self):
        original = self.h.submit(**self.scope, request={"content": "x"})
        self.h.forget(**self.scope)
        self.assertEqual(self.h.current(**self.scope), "tombstoned")
        self.assertEqual(len(self.h.history), 1)
        with self.assertRaises(ValueError):
            self.h.submit(**self.scope, request={"content": "different-before-retry"})
        self.assertEqual(self.h.submit(**self.scope, request={"content": "x"}), original)
        with self.assertRaises(ValueError):
            self.h.submit(**self.scope, request={"content": "new"})
    def test_incomplete_history_blocks_new(self):
        with self.assertRaises(ValueError):
            self.h.submit(**self.scope, request={}, history_complete=False)
    def test_scope_isolation(self):
        a = self.h.submit(**self.scope, request={})
        other = dict(self.scope, principal="bob")
        b = self.h.submit(**other, request={})
        self.assertNotEqual(a, b)

class VerificationTests(unittest.TestCase):
    def test_content_bound_and_no_self_proof(self):
        values = dict(subject_revision=1, subject_sha="hash", proof_revision=1, proof_sha="hash", verifier_id="tool-a", source_id="speaker-a", scope_covers=True, method_allowed=True, credential_exists=True, credential_time=10, verified_at=20)
        self.assertTrue(verification_eligible(**values))
        for patch in ({"proof_sha": "old"}, {"proof_revision": 2}, {"verifier_id": "speaker-a"}, {"credential_time": 20}, {"scope_covers": False}, {"credential_exists": False}):
            self.assertFalse(verification_eligible(**dict(values, **patch)))

class ReviewRegressionTests(unittest.TestCase):
    def test_request_key_types_do_not_collide(self):
        for bad in ({1: "a"}, {"x": (1, 2)}, {"x": 1.0}):
            with self.assertRaises(ValueError): request_fingerprint(bad)
        self.assertNotEqual(request_fingerprint({"x": True}), request_fingerprint({"x": 1}))
    def test_boolean_hash_not_string_hash(self):
        args = dict(subject_revision=1, subject_sha=1, proof_revision=1, proof_sha=True, verifier_id="tool", source_id="source", scope_covers=True, method_allowed=True, credential_exists=True, credential_time=1, verified_at=2)
        self.assertFalse(verification_eligible(**args))
        self.assertFalse(verification_eligible(**dict(args, subject_sha="x", proof_sha="x", verifier_id=3)))
    def test_cycle_in_independent_evidence_rejected(self):
        nodes = {"a": node("a", edges=(edge("b", "corroborating"),)), "b": node("b", edges=(edge("a", "contradicting"),))}
        self.assertTrue(Model().decision("a", nodes).quarantined)
        self.assertFalse(Model().append_allowed("a", edge("a", "corroborating"), {"a": node("a")}))

class SpecTests(unittest.TestCase):
    def test_duplicate_keys_rejected(self):
        with self.assertRaises(ValueError):
            parse('{"a":1,"a":2}')
    def test_unknown_fields_rejected(self):
        s = load();s["unused"] = True
        with self.assertRaises(ValueError): validate(s)
    def test_three_historical_semantic_mutations_fail(self):
        base = load()
        lock = dict(spec_version=base["spec_version"], sha256=digest(base), previous_sha256=None, reason="independent fixture")
        for section, key, value in (("formation", "quantifier", "all"), ("sensitivity", "clearance_operator", "lte"), ("verification", "source_identity_operands", ["verifier_id", "verifier_id"])):
            s = copy.deepcopy(base);s[section][key] = value
            self.assertIn("full spec digest drift", freeze_errors(s, lock))
            with self.assertRaises(ValueError): validate(s)
    def test_boolean_not_integer_schema(self):
        s = load();s["schema_version"] = True
        with self.assertRaises(ValueError): validate(s)

if __name__ == "__main__":
    unittest.main()
