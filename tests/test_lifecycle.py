"""Independent expected tests for LifecycleSandbox, EpochDecisionCache, and private BM25."""
import hashlib
import unittest
from framework.model import Edge, EpochDecisionCache, Model, Node, can_read_with_epoch_cache
from sandbox_runtime.lifecycle import LifecycleSandbox
from sandbox_runtime.retrieval import PrivateBM25Store
from sandbox_runtime.store import Probe

A = "2024-01-01T00:00:00Z"
B = "2024-01-10T00:00:00Z"
Q = "2024-01-05T00:00:00Z"


def ctx(principal="alice", tenant="t1", clearance=2, auth_epoch=1, policy_generation=1, expires_at=100):
    return {
        "tenant": tenant,
        "principal": principal,
        "clearance": clearance,
        "auth_epoch": auth_epoch,
        "policy_generation": policy_generation,
        "expires_at": expires_at,
    }


def cspace(attrs=None, unknown_carrier=False):
    return {
        "carrier": {"state": "unknown"} if unknown_carrier else {"state": "declared", "text": "md"},
        "method": {"state": "declared", "text": "exact"},
        "existence": {"state": "declared", "text": "present"},
        "attributes": list(attrs or []),
    }


def bitemp(obs_s=A, obs_e=B, eff_s=A, eff_e=B):
    return {
        "observed": {"start": {"state": "instant", "value": obs_s}, "end": {"state": "instant", "value": obs_e}},
        "effective": {"start": {"state": "instant", "value": eff_s}, "end": {"state": "instant", "value": eff_e}},
    }


def write_req(token, body, *, sensitivity=1, readers=("alice", "bob"), attrs=None, kind="Write.create", node_id=None, expected_revision=None, edges=()):
    r = {
        "kind": kind,
        "caller_token": token,
        "content": body,
        "declared_sensitivity": sensitivity,
        "reader_ceiling": sorted(set(readers)),
        "source_edges": list(edges),
        "condition_space": cspace(attrs),
        "bitemporal": bitemp(),
        "source_attribution": {"source_kind": "human", "source_id": "author-1"},
        "durability_request": "process",
    }
    if kind == "Write.modify":
        r["node_id"] = node_id
        r["expected_revision"] = expected_revision
    return r


class EpochCacheTests(unittest.TestCase):
    def test_epoch_cache_matches_uncached_across_mutations(self):
        m = Model()
        cache = EpochDecisionCache()
        r = frozenset({"alice", "bob"})
        nodes = {
            "root": Node("t1", 1, "h-root", 1, r, r),
            "child": Node("t1", 1, "h-child", 1, r, r, edges=(Edge("root", "derived", 1, "h-root"),)),
        }
        self.assertTrue(can_read_with_epoch_cache(m, "child", nodes, tenant="t1", principal="bob", clearance=2, graph_epoch=1, cache=cache))
        nodes["root"] = Node("t1", 1, "h-root", 1, r, frozenset({"alice"}))
        self.assertFalse(can_read_with_epoch_cache(m, "child", nodes, tenant="t1", principal="bob", clearance=2, graph_epoch=2, cache=cache))
        self.assertTrue(can_read_with_epoch_cache(m, "child", nodes, tenant="t1", principal="alice", clearance=1, graph_epoch=2, cache=cache))
        self.assertFalse(can_read_with_epoch_cache(m, "child", nodes, tenant="t1", principal="alice", clearance=0, graph_epoch=2, cache=cache))
        nodes["root"] = Node("t1", 1, "h-root", 1, r, frozenset({"alice"}), tombstoned=True)
        self.assertFalse(can_read_with_epoch_cache(m, "child", nodes, tenant="t1", principal="alice", clearance=3, graph_epoch=3, cache=cache))


class PrivateBM25Tests(unittest.TestCase):
    def test_bm25_ignores_hidden_doc_df_and_avgdl(self):
        base_rows = [
            dict(id="doc-a", revision=1, tenant="t1", sensitivity=1, creation_readers=["alice"], current_readers=["alice"],
                 edges=[], tombstoned=False, body="quantum memory safety", key="k1", architecture="a", version="v1", conditions={}),
            dict(id="doc-b", revision=1, tenant="t1", sensitivity=1, creation_readers=["alice"], current_readers=["alice"],
                 edges=[], tombstoned=False, body="memory safety", key="k2", architecture="a", version="v1", conditions={}),
        ]
        hidden_rows = [
            dict(id=f"hid-{i}", revision=1, tenant="t2" if i % 2 == 0 else "t1", sensitivity=1,
                 creation_readers=["bob"], current_readers=["bob"], edges=[], tombstoned=False,
                 body=("quantum " * 200) + "extra noise words", key=f"hk.{i}", architecture="a", version="v1", conditions={})
            for i in range(40)
        ]
        c_alice = ctx(principal="alice", tenant="t1")
        s_clean = PrivateBM25Store(base_rows, synthetic=True, probe=Probe())
        s_polluted = PrivateBM25Store(base_rows + hidden_rows, synthetic=True, probe=Probe())
        hits_clean = s_clean.search_bm25("quantum memory", c_alice, 1)
        hits_polluted = s_polluted.search_bm25("quantum memory", c_alice, 1)
        self.assertEqual(hits_clean, hits_polluted)
        self.assertEqual([h["id"] for h in hits_clean], ["doc-a", "doc-b"])


class LifecycleEndToEndTests(unittest.TestCase):
    def test_write_modify_idempotency_conflict_and_govern_lifecycle(self):
        sb = LifecycleSandbox(synthetic=True)
        c_alice = ctx("alice")
        r1 = sb.execute(write_req("t1", "alpha rule"), c_alice, 10)
        self.assertEqual(r1["outcome"], "ok")
        self.assertEqual(r1["historical_receipt"]["node_id"], "node-1")
        r1_dup = sb.execute(write_req("t1", "alpha rule"), c_alice, 11)
        self.assertEqual(r1_dup["historical_receipt"], r1["historical_receipt"])
        r1_conf = sb.execute(write_req("t1", "tampered rule"), c_alice, 12)
        self.assertEqual(r1_conf["error_code"], "TOKEN_PAYLOAD_CONFLICT")
        r_stale = sb.execute(write_req("t2", "beta rule", kind="Write.modify", node_id="node-1", expected_revision=99), c_alice, 13)
        self.assertEqual(r_stale["error_code"], "REVISION_CONFLICT")
        r2 = sb.execute(write_req("t2", "beta rule", kind="Write.modify", node_id="node-1", expected_revision=1), c_alice, 14)
        self.assertEqual(r2["historical_receipt"]["revision"], 2)
        fg = sb.execute({"kind": "Govern.forget", "caller_token": "tg1", "node_id": "node-1", "expected_revision": 2, "reason": "obsolete"}, c_alice, 15)
        self.assertEqual(fg["target"]["projection"], "tombstoned")
        rcpt = sb.execute({"kind": "Read.receipt", "operation": "Write.modify", "caller_token": "t2"}, c_alice, 16)
        self.assertEqual(rcpt["target"]["commit_status"], "committed")
        self.assertEqual(rcpt["target"]["projection"], "unknown")
        rst_fail = sb.execute({"kind": "Govern.restore", "caller_token": "tg2", "node_id": "node-1", "expected_revision": 2, "reason": "re-enable"}, c_alice, 17)
        self.assertEqual(rst_fail["error_code"], "VERIFICATION_REQUIRED")
        # Self-verification and insufficient scope ("read") both rejected
        self.assertFalse(sb.verify_record(node_id="node-1", expected_revision=2, verifier_id="author-1", scope="full", method_allowed=True, credential_exists=True, credential_time=5, verified_at=18))
        self.assertFalse(sb.verify_record(node_id="node-1", expected_revision=2, verifier_id="auditor-9", scope="read", method_allowed=True, credential_exists=True, credential_time=5, verified_at=18))
        rst_still_blocked = sb.execute({"kind": "Govern.restore", "caller_token": "tg2b", "node_id": "node-1", "expected_revision": 2, "reason": "re-enable"}, c_alice, 18)
        self.assertEqual(rst_still_blocked["error_code"], "VERIFICATION_REQUIRED")
        self.assertTrue(sb.verify_record(node_id="node-1", expected_revision=2, verifier_id="auditor-9", scope="restore", method_allowed=True, credential_exists=True, credential_time=5, verified_at=18))
        rst_ok = sb.execute({"kind": "Govern.restore", "caller_token": "tg3", "node_id": "node-1", "expected_revision": 2, "reason": "re-enable"}, c_alice, 19)
        self.assertEqual(rst_ok["target"]["projection"], "active")

    def test_cancel_fence_epoch_and_mixed_match_defer_blocked(self):
        sb = LifecycleSandbox(synthetic=True)
        c_alice = ctx("alice")
        cancel_res = sb.execute({"kind": "Operation.cancel", "target_operation": "Write.create", "caller_token": "tok-c", "fencing_epoch": 5, "reason": "abort"}, c_alice, 10)
        self.assertEqual(cancel_res["error_code"], "CANCELLED")
        # Stale lower-epoch cancel fails with STATE_CONFLICT; same/higher epoch returns CANCELLED
        stale_c = sb.execute({"kind": "Operation.cancel", "target_operation": "Write.create", "caller_token": "tok-c", "fencing_epoch": 4, "reason": "late"}, c_alice, 10)
        self.assertEqual(stale_c["error_code"], "STATE_CONFLICT")
        w_after = sb.execute(write_req("tok-c", "late write"), c_alice, 11)
        self.assertEqual(w_after["error_code"], "CANCELLED")
        # Mixed MATCH + DEFER candidates on same query MUST fail closed (CONDITION_DEFERRED)
        self.assertEqual(sb.execute(write_req("tok-m", "alpha beta"), c_alice, 12)["outcome"], "ok")
        unk_w = write_req("tok-u", "alpha beta")
        unk_w["condition_space"] = cspace(unknown_carrier=True)
        self.assertEqual(sb.execute(unk_w, c_alice, 13)["outcome"], "ok")
        read_defer = sb.execute({"kind": "Read.search", "query": "alpha", "limit": 5, "include_provenance": False, "condition_query": cspace(), "time_axis": "effective", "time_point": Q}, c_alice, 14)
        self.assertEqual(read_defer["error_code"], "CONDITION_DEFERRED")
        self.assertIsNone(read_defer["records"])

    def test_recovery_and_retention_integration(self):
        sb = LifecycleSandbox(synthetic=True)
        self.assertEqual(sb.simulate_recovery(body_present=False, audit_present=False, matching=True, authoritative_negative=False, history_complete=True)["status"], "unknown")
        self.assertEqual(sb.simulate_recovery(body_present=False, audit_present=False, matching=True, authoritative_negative=True, history_complete=True)["status"], "absent")
        self.assertEqual(sb.simulate_recovery(body_present=True, audit_present=False, matching=False, authoritative_negative=False, history_complete=True)["integrity_failure"], True)
        self.assertEqual(sb.retention_check({"kind": "token_final", "lifecycle": "tombstoned", "deadline": 1, "authorized": True, "legal_hold": False, "commit_resolved": True, "terminal_durable": True, "dependencies_closed": True, "audit_closed": True}, 100), "retain")

    def test_power_rejected_and_correct_revision_validates_edges_and_policy(self):
        sb = LifecycleSandbox(synthetic=True)
        c_alice = ctx("alice")
        pwr = write_req("tok-pwr", "power write")
        pwr["durability_request"] = "power"
        self.assertEqual(sb.execute(pwr, c_alice, 10)["error_code"], "POWER_UNSUPPORTED")
        self.assertEqual(sb.execute(write_req("tok-1", "v1 body", sensitivity=2, readers=("alice",)), c_alice, 11)["outcome"], "ok")
        # Attempting correct_revision with dangling edge MUST fail closed and NOT commit revision 2
        rep_bad_edge = write_req("unused", "v2 bad edge", sensitivity=2, readers=("alice",), edges=[{"node_id": "missing", "revision": 1, "content_sha": "a" * 64, "relation": "derived"}])
        rep_bad_edge = {k: v for k, v in rep_bad_edge.items() if k not in ("kind", "caller_token", "durability_request")}
        bad_cor = sb.execute({"kind": "Govern.correct_revision", "caller_token": "tg-bad", "node_id": "node-1", "expected_revision": 1, "reason": "bad", "replacement": rep_bad_edge}, c_alice, 12)
        self.assertEqual(bad_cor["error_code"], "INVALID_ARGUMENT")
        self.assertEqual(sb._records["node-1"]["revision"], 1)
        # Attempting correct_revision to lower sensitivity or expand readers -> POLICY_WIDENING_UNSUPPORTED
        rep_widen = write_req("unused", "v2 widen", sensitivity=1, readers=("alice", "bob"))
        rep_widen = {k: v for k, v in rep_widen.items() if k not in ("kind", "caller_token", "durability_request")}
        widen_cor = sb.execute({"kind": "Govern.correct_revision", "caller_token": "tg-w", "node_id": "node-1", "expected_revision": 1, "reason": "widen", "replacement": rep_widen}, c_alice, 13)
        self.assertEqual(widen_cor["error_code"], "POLICY_WIDENING_UNSUPPORTED")
        # Valid correct_revision succeeds
        rep_ok = write_req("unused", "v2 corrected body", sensitivity=2, readers=("alice",))
        rep_ok = {k: v for k, v in rep_ok.items() if k not in ("kind", "caller_token", "durability_request")}
        cor = sb.execute({"kind": "Govern.correct_revision", "caller_token": "tg-cor", "node_id": "node-1", "expected_revision": 1, "reason": "fix", "replacement": rep_ok}, c_alice, 14)
        self.assertEqual(cor["historical_receipt"]["revision"], 2)

    def test_cursor_invalidation_toctou_and_end_to_end_cache_eviction(self):
        sb = LifecycleSandbox(synthetic=True)
        c_alice = ctx("alice")
        c_bob = ctx("bob")
        self.assertEqual(sb.execute(write_req("p1", "memory item alpha"), c_alice, 10)["outcome"], "ok")
        self.assertEqual(sb.execute(write_req("p2", "memory item beta"), c_alice, 11)["outcome"], "ok")
        # Search by node id ("node-1") matches pre-filter & BM25 consistently
        id_hit = sb.execute({"kind": "Read.search", "query": "node-1", "limit": 5, "include_provenance": False, "condition_query": cspace(), "time_axis": "effective", "time_point": Q}, c_alice, 12)
        self.assertEqual(id_hit["records"][0]["locator"]["id"], "node-1")
        # Pagination page 1
        page1 = sb.execute({"kind": "Read.search", "query": "memory", "limit": 1, "include_provenance": True, "condition_query": cspace(), "time_axis": "effective", "time_point": Q}, c_alice, 12)
        self.assertIsNotNone(page1["next_cursor"])
        # Bob could read node-1 before policy tightening; after change_policy(alice only), both cache & cursor invalidate immediately
        self.assertEqual(sb.execute({"kind": "Read.get", "node_id": "node-1", "include_provenance": False, "condition_query": cspace(), "time_axis": "effective", "time_point": Q}, c_bob, 13)["outcome"], "ok")
        sb.execute({"kind": "Govern.change_policy", "caller_token": "pol-1", "node_id": "node-1", "expected_revision": 1, "reason": "tighten", "declared_sensitivity": 2, "reader_ceiling": ["alice"]}, c_alice, 14)
        c_alice_p2 = ctx("alice", policy_generation=sb.policy_generation)
        c_bob_p2 = ctx("bob", policy_generation=sb.policy_generation)
        self.assertEqual(sb.execute({"kind": "Read.get", "node_id": "node-1", "include_provenance": False, "condition_query": cspace(), "time_axis": "effective", "time_point": Q}, c_bob_p2, 15)["error_code"], "NOT_FOUND_OR_DENIED")
        stale_pol = sb.execute({"kind": "Read.search", "query": "memory", "limit": 1, "include_provenance": True, "condition_query": cspace(), "time_axis": "effective", "time_point": Q, "cursor": page1["next_cursor"]}, c_alice_p2, 15)
        self.assertEqual(stale_pol["error_code"], "POLICY_CHANGED")
        # New cursor then write bumps content_generation -> old cursor invalidated too
        page1_new = sb.execute({"kind": "Read.search", "query": "memory", "limit": 1, "include_provenance": True, "condition_query": cspace(), "time_axis": "effective", "time_point": Q}, c_alice_p2, 16)
        self.assertEqual(sb.execute(write_req("p3", "memory item gamma"), c_alice_p2, 17)["outcome"], "ok")
        stale_content = sb.execute({"kind": "Read.search", "query": "memory", "limit": 1, "include_provenance": True, "condition_query": cspace(), "time_axis": "effective", "time_point": Q, "cursor": page1_new["next_cursor"]}, c_alice_p2, 18)
        self.assertEqual(stale_content["error_code"], "POLICY_CHANGED")
        # Non-tautological TOCTOU check: context expires/changes between prepare and emit commit
        toctou = sb.execute(
            {"kind": "Read.get", "node_id": "node-1", "include_provenance": False, "condition_query": cspace(), "time_axis": "effective", "time_point": Q},
            c_alice_p2, 19,
            current_context_provider=lambda: ctx("alice", auth_epoch=99, policy_generation=sb.policy_generation),
        )
        self.assertEqual(toctou["error_code"], "POLICY_CHANGED")


if __name__ == "__main__":
    unittest.main()
