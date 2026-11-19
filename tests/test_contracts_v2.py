"""Independent expected tests and adversarial boundary checks for api_v2 and response_full."""
import copy
import hashlib
import unittest
from framework import contracts as ct
from framework import responses as resp

A = "2024-01-01T00:00:00Z"
B = "2024-01-02T00:00:00Z"
SHA = hashlib.sha256(b"hello world").hexdigest()


def cspace(attrs=None):
    return {
        "carrier": {"state": "declared", "text": "markdown"},
        "method": {"state": "declared", "text": "exact"},
        "existence": {"state": "declared", "text": "present"},
        "attributes": list(attrs or []),
    }


def bitemp(start=A, end=B):
    return {
        "observed": {"start": {"state": "instant", "value": start}, "end": {"state": "instant", "value": end}},
        "effective": {"start": {"state": "instant", "value": start}, "end": {"state": "unbounded"}},
    }


def ok_read_resp():
    loc = {"id": "n1", "revision": 1, "content_sha": SHA}
    return {
        "version": "0.2-full",
        "request_id": "req-1",
        "scope": "read",
        "outcome": "ok",
        "error_code": None,
        "next_action": "none",
        "snapshot_ref": "snap-1",
        "policy_generation": 1,
        "records": [ct.build_untrusted_record(loc, "hello world", {"source_kind": "human", "source_id": "u1", "redacted_edges": 0})],
        "next_cursor": None,
        "target": None,
        "historical_receipt": None,
        "selfcheck_aggregate": None,
    }


class ContractsV2Tests(unittest.TestCase):
    def test_v2_all_12_variants(self):
        base_write = {
            "caller_token": "tok-1",
            "content": "hello",
            "declared_sensitivity": 1,
            "reader_ceiling": ["alice", "bob"],
            "source_edges": [],
            "condition_space": cspace([{"key": "region", "value": "east"}]),
            "bitemporal": bitemp(),
            "source_attribution": {"source_kind": "human", "source_id": "alice"},
            "durability_request": "process",
        }
        replacement = {k: v for k, v in base_write.items() if k not in ("caller_token", "durability_request")}
        gov_base = {"caller_token": "tok-g", "node_id": "n1", "expected_revision": 1, "reason": "policy update"}
        reqs = [
            dict(base_write, kind="Write.create"),
            dict(base_write, kind="Write.modify", node_id="n1", expected_revision=1),
            {"kind": "Read.get", "node_id": "n1", "include_provenance": False, "condition_query": cspace(), "time_axis": "observed", "time_point": A},
            {"kind": "Read.search", "query": "hello", "limit": 10, "include_provenance": True, "condition_query": cspace(), "time_axis": "effective", "time_point": A},
            {"kind": "Read.expand", "node_id": "n1", "depth": 2, "limit": 10, "include_provenance": False, "condition_query": cspace(), "time_axis": "effective", "time_point": A},
            {"kind": "Read.receipt", "operation": "Write.create", "caller_token": "tok-1"},
            dict(gov_base, kind="Govern.forget"),
            dict(gov_base, kind="Govern.restore"),
            dict(gov_base, kind="Govern.correct_revision", replacement=replacement),
            dict(gov_base, kind="Govern.change_policy", declared_sensitivity=2, reader_ceiling=["alice"]),
            {"kind": "Operation.cancel", "target_operation": "Write.create", "caller_token": "tok-1", "fencing_epoch": 2, "reason": "timeout abort"},
            {"kind": "SelfCheck", "check_ids": ["C01", "R01"], "scope": "isolated-runtime", "snapshot_ref": "snap-1"},
        ]
        self.assertEqual(len(reqs), 12)
        for r in reqs:
            with self.subTest(kind=r["kind"]):
                self.assertEqual(ct.validate_v2_request(r), r)

    def test_v2_rejects_duplicate_attr_keys_invalid_dates_and_missing_axis(self):
        bad_write = {
            "kind": "Write.create",
            "caller_token": "tok-1",
            "content": "hello",
            "declared_sensitivity": 1,
            "reader_ceiling": ["alice"],
            "source_edges": [],
            "condition_space": cspace([{"key": "k", "value": "1"}, {"key": "k", "value": "2"}]),
            "bitemporal": bitemp(),
            "source_attribution": {"source_kind": "human", "source_id": "alice"},
            "durability_request": "process",
        }
        with self.assertRaises(ValueError):
            ct.validate_v2_request(bad_write)
        bad_time = copy.deepcopy(bad_write)
        bad_time["condition_space"] = cspace()
        bad_time["bitemporal"] = bitemp(start=B, end=A)
        with self.assertRaises(ValueError):
            ct.validate_v2_request(bad_time)
        bad_read = {
            "kind": "Read.get",
            "node_id": "n1",
            "include_provenance": False,
            "condition_query": cspace(),
            "time_axis": "auto",
            "time_point": A,
        }
        with self.assertRaises(ValueError):
            ct.validate_v2_request(bad_read)

    def test_full_response_enforces_untrusted_records_and_no_leak_on_error(self):
        good = ok_read_resp()
        self.assertEqual(ct.validate_full_response(good), good)
        # Non-ok READ_FAILED must NEVER carry records or historical_receipt
        bad_err = copy.deepcopy(good)
        bad_err["outcome"] = "error"
        bad_err["error_code"] = "READ_FAILED"
        bad_err["next_action"] = "retry_read"
        with self.assertRaises(ValueError):
            ct.validate_full_response(bad_err)
        bad_read_rcpt = copy.deepcopy(bad_err)
        bad_read_rcpt["records"] = None
        bad_read_rcpt["historical_receipt"] = {
            "commit_status": "committed", "fingerprint": SHA, "node_id": "n1",
            "revision": 1, "content_sha": SHA, "durability_actual": "process", "audit_state": "ok", "writer_id": "fixture-a"
        }
        with self.assertRaises(ValueError):
            ct.validate_full_response(bad_read_rcpt)
        # Non-read scope (e.g. ok mutation) must NEVER carry records
        bad_mut_rec = copy.deepcopy(good)
        bad_mut_rec["scope"] = "mutation"
        bad_mut_rec["snapshot_ref"] = None
        bad_mut_rec["policy_generation"] = None
        with self.assertRaises(ValueError):
            ct.validate_full_response(bad_mut_rec)
        # Read scope must NEVER carry target (neither ok nor READ_FAILED)
        for outcome, code, action, recs in (
            ("ok", None, "none", good["records"]),
            ("error", "READ_FAILED", "retry_read", None),
        ):
            bad_read_target = copy.deepcopy(good)
            bad_read_target["outcome"] = outcome
            bad_read_target["error_code"] = code
            bad_read_target["next_action"] = action
            bad_read_target["records"] = recs
            bad_read_target["target"] = {"commit_status": "committed", "audit": "ok", "projection": "active", "negative_basis": "unassessed"}
            with self.assertRaises(ValueError):
                ct.validate_full_response(bad_read_target)
        # Denied receipt must NEVER disclose target or receipt metadata
        bad_denied = {
            "version": "0.2-full",
            "request_id": "req-d",
            "scope": "receipt",
            "outcome": "error",
            "error_code": "NOT_FOUND_OR_DENIED",
            "next_action": "authenticate",
            "snapshot_ref": None,
            "policy_generation": None,
            "records": None,
            "next_cursor": None,
            "target": {"commit_status": "committed", "audit": "ok", "projection": "active", "negative_basis": "unassessed"},
            "historical_receipt": None,
            "selfcheck_aggregate": None,
        }
        with self.assertRaises(ValueError):
            ct.validate_full_response(bad_denied)
        # Tampered body sha rejected
        bad_sha = copy.deepcopy(good)
        bad_sha["records"][0]["body"] = "tampered"
        with self.assertRaises(ValueError):
            ct.validate_full_response(bad_sha)
        # Bidi spoofing character rejected in BOTH build_untrusted_record and direct validate_full_response
        for ch in ("‮", "؜"):
            spoof = "ab" + ch + "cd"
            spoof_sha = hashlib.sha256(spoof.encode("utf-8")).hexdigest()
            with self.assertRaises(ValueError):
                ct.build_untrusted_record({"id": "n1", "revision": 1, "content_sha": spoof_sha}, spoof)
            handcrafted = copy.deepcopy(good)
            handcrafted["records"][0]["body"] = spoof
            handcrafted["records"][0]["body_sha"] = spoof_sha
            handcrafted["records"][0]["locator"]["content_sha"] = spoof_sha
            with self.assertRaises(ValueError):
                ct.validate_full_response(handcrafted)

    def test_cancel_and_selfcheck_response_semantics(self):
        cancel_ok = {
            "version": "0.2-full",
            "request_id": "req-c",
            "scope": "cancel",
            "outcome": "error",
            "error_code": "CANCELLED",
            "next_action": "return_original_cancel",
            "snapshot_ref": None,
            "policy_generation": None,
            "records": None,
            "next_cursor": None,
            "target": {"commit_status": "absent", "audit": "unknown", "projection": "unknown", "negative_basis": "durable_cancel"},
            "historical_receipt": None,
            "selfcheck_aggregate": None,
        }
        self.assertEqual(ct.validate_full_response(cancel_ok), cancel_ok)
        bad_cancel = copy.deepcopy(cancel_ok)
        bad_cancel["target"]["commit_status"] = "committed"
        with self.assertRaises(ValueError):
            ct.validate_full_response(bad_cancel)

    def test_responses_schema_cache_is_isolated_copy(self):
        s1 = resp._load_resp_schema()
        s1["properties"]["version"]["format"] = "injected"
        s2 = resp._load_resp_schema()
        self.assertNotIn("format", s2["properties"]["version"])
        good = resp.read_response("r1", True, True)
        self.assertEqual(resp.validate_envelope(good), good)


if __name__ == "__main__":
    unittest.main()
