"""Independent API proposal examples: inputs and expected outcomes are hand-written."""
import copy
import json
import unittest
from unittest.mock import patch
from framework import api


def create():
    return {"kind": "Write.create", "caller_token": "tok", "content": "合成内容",
            "declared_sensitivity": 1, "reader_ceiling": ["alice", "bob"], "source_edges": [],
            "conditions": [], "source_attribution": {"source_kind": "human", "source_id": "source"}, "durability_request": "process"}


def search():
    return {"kind": "Read.search", "query": "synthetic", "limit": 5, "include_provenance": False}


def binding():
    return {"tenant": "T", "principal": "alice", "read_kind": "Read.search", "query_sha": "a" * 64, "snapshot": "s1", "policy_generation": 7}


class ApiTests(unittest.TestCase):
    def test_all_variants(self):
        c = create()
        replacement = {k: v for k, v in c.items() if k not in ("kind", "caller_token", "durability_request")}
        gov = {"caller_token": "g", "node_id": "n", "expected_revision": 1, "reason": "合成原因"}
        examples = [c, dict(c, kind="Write.modify", node_id="n", expected_revision=1), search(),
                    {"kind": "Read.expand", "node_id": "n", "depth": 2, "limit": 5, "include_provenance": True},
                    {"kind": "Read.get", "node_id": "n", "include_provenance": False},
                    {"kind": "Read.receipt", "operation": "Write.create", "caller_token": "tok"},
                    dict(gov, kind="Govern.forget"), dict(gov, kind="Govern.restore"),
                    dict(gov, kind="Govern.correct_revision", replacement=replacement),
                    dict(gov, kind="Govern.change_policy", declared_sensitivity=2, reader_ceiling=["alice"]),
                    {"kind": "SelfCheck", "check_ids": ["C01", "R01"], "scope": "isolated-runtime", "snapshot_ref": "s"}]
        for value in examples:
            with self.subTest(kind=value["kind"]):
                self.assertEqual(api.validate_request(value), value)
                self.assertEqual(api.parse_request(json.dumps(value, ensure_ascii=False)), value)

    def test_required_and_unknown_each_variant(self):
        schema = api.load_schema()
        for variant in schema["oneOf"]:
            kind = variant["properties"]["kind"]["const"]
            # Missing every required field: no valid object may be accepted.
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError): api.validate_request({"kind": kind})
        for field in ("tenant", "principal", "clearance", "authorized", "policy_safe", "op"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError): api.validate_request(dict(create(), **{field: "forged"}))
        c = create(); c["source_attribution"]["principal"] = "forged"
        with self.assertRaises(ValueError): api.validate_request(c)

    def test_create_modify_separation(self):
        for v in (dict(create(), node_id="n"), dict(create(), expected_revision=1), dict(create(), kind="Write.modify")):
            with self.assertRaises(ValueError): api.validate_request(v)

    def test_strict_integer(self):
        for v in (True, False, 1.0, -1, 4, 9007199254740992):
            with self.subTest(v=v):
                with self.assertRaises(ValueError): api.validate_request(dict(create(), declared_sensitivity=v))
        for v in (True, 0, 1.0):
            with self.assertRaises(ValueError): api.validate_request(dict(create(), kind="Write.modify", node_id="n", expected_revision=v))

    def test_duplicate_keys_nested(self):
        with self.assertRaises(ValueError): api.parse_request('{"kind":"Read.get","kind":"Read.search"}')
        text = json.dumps(create()).replace('"source_id": "source"', '"source_id": "source", "source_id": "other"')
        with self.assertRaises(ValueError): api.parse_request(text)

    def test_edge_binding(self):
        edge = {"node_id": "source", "revision": 1, "content_sha": "a" * 64, "relation": "derived"}
        self.assertEqual(api.validate_request(dict(create(), source_edges=[edge]))["source_edges"], [edge])
        for field, val in (("revision", True), ("content_sha", "a" * 63), ("relation", "retracted")):
            with self.assertRaises(ValueError): api.validate_request(dict(create(), source_edges=[dict(edge, **{field: val})]))
        edge.pop("content_sha")
        with self.assertRaises(ValueError): api.validate_request(dict(create(), source_edges=[edge]))

    def test_readers_sorted_unique_at_all_levels(self):
        for readers in ([], ["alice", "alice"], ["bob", "alice"]):
            with self.assertRaises(ValueError): api.validate_request(dict(create(), reader_ceiling=readers))
        replacement = {k: v for k, v in create().items() if k not in ("kind", "caller_token", "durability_request")}
        replacement["reader_ceiling"] = ["bob", "alice"]
        with self.assertRaises(ValueError): api.validate_request({"kind":"Govern.correct_revision", "caller_token":"t", "node_id":"n", "expected_revision":1, "reason":"r", "replacement":replacement})

    def test_resource_limits(self):
        for text in (' ' * 131073, '[' * 1000 + '0' + ']' * 1000):
            with self.assertRaises(ValueError): api.parse_request(text)
        with self.assertRaises(ValueError): api.validate_request(dict(create(), content="界" * 50000))
        with self.assertRaises(ValueError): api.validate_request(dict(create(), conditions=["x"] * 33))
        for n in (0, 101, True):
            with self.assertRaises(ValueError): api.validate_request(dict(search(), limit=n))

    def test_non_json_and_unicode(self):
        for v in (float("nan"), 1.2, (1,), {1: "value"}, chr(0xD800)):
            with self.subTest(v=repr(v)):
                with self.assertRaises(ValueError): api.validate_request(dict(create(), content=v))
        with self.assertRaises(ValueError): api.parse_request(chr(0xD800))

    def test_copy_and_full_fingerprint(self):
        c = create(); returned = api.validate_request(c); returned["reader_ceiling"].append("zoe")
        self.assertEqual(c["reader_ceiling"], ["alice", "bob"])
        self.assertEqual(api.request_digest(c), api.request_digest(dict(reversed(list(c.items())))))
        changes = {"caller_token": "other", "content": "changed", "declared_sensitivity": 2, "reader_ceiling": ["alice"], "conditions": ["condition"], "durability_request": "power"}
        for k, v in changes.items():
            self.assertNotEqual(api.request_digest(c), api.request_digest(dict(c, **{k:v})))
        self.assertNotEqual(api.request_digest(dict(c, content="é")), api.request_digest(dict(c, content="e" + chr(769))))

    def test_query_digest_complete(self):
        s = search()
        self.assertEqual(api.query_digest(s), api.query_digest(dict(s, cursor="opaque")))
        for k,v in (("query", "other"), ("limit", 6), ("include_provenance", True)):
            self.assertNotEqual(api.query_digest(s), api.query_digest(dict(s, **{k:v})))
        e = {"kind":"Read.expand", "node_id":"n", "depth":2, "limit":5, "include_provenance":False}
        self.assertNotEqual(api.query_digest(e), api.query_digest(dict(e, depth=3)))

    def test_cursor_every_binding(self):
        b = binding(); cursor = dict(b, expires_at=100)
        self.assertTrue(api.cursor_valid(cursor, b, 99))
        self.assertFalse(api.cursor_valid(cursor, b, 100))
        for k in b:
            changed = dict(b); changed[k] = 8 if k == "policy_generation" else ("Read.expand" if k == "read_kind" else "other")
            with self.subTest(k=k): self.assertFalse(api.cursor_valid(cursor, changed, 99))
        self.assertFalse(api.cursor_valid(dict(cursor, policy_generation=True), b, 99))
        self.assertFalse(api.cursor_valid(dict(cursor, extra=1), b, 99))
        self.assertFalse(api.cursor_valid(cursor, b, True))
        self.assertFalse(api.cursor_valid(dict(cursor, expires_at=True), b, 0))

    def test_receipt_caller_scope(self):
        context = {"tenant":"T", "principal":"alice"};scope=("T","alice","Write.create","token")
        self.assertTrue(api.receipt_scope_allowed(context,scope,"Write.create","token"))
        for index in range(4):
            changed=list(scope);changed[index]="other"
            self.assertFalse(api.receipt_scope_allowed(context,tuple(changed),"Write.create","token"))
        self.assertFalse(api.receipt_scope_allowed({"tenant":"T","principal":"alice","role":"admin"},scope,"Write.create","token"))

    def test_unknown_only_query(self):
        self.assertEqual(api.retry_action("unknown", True, True), "query_only")
        self.assertEqual(api.retry_action("absent", True, False), "query_only")
        self.assertEqual(api.retry_action("committed", True, True), "return_original")
        self.assertEqual(api.retry_action("committed", False, True), "conflict")
        self.assertEqual(api.retry_action("absent", True, True), "eligible_for_authorized_first_apply")
        with self.assertRaises(ValueError): api.retry_action("unknown", True, "yes")

    def test_govern_positive(self):
        self.assertEqual(api.govern_transition("active",2,2,"forget",True,True,True), ("tombstoned",))
        self.assertEqual(api.govern_transition("tombstoned",2,2,"restore",True,True,True), ("active",))
        self.assertEqual(api.govern_transition("active",2,2,"correct_revision",True,True,False), ("superseded","new_active"))
        self.assertEqual(api.govern_transition("active",2,2,"change_policy",True,True,True), ("active",))

    def test_govern_denial_matrix(self):
        cases=[("active",2,1,"forget",True,True,True), ("active",2,2,"forget",False,True,True),
               ("active",2,2,"restore",True,True,True), ("superseded",2,2,"restore",True,True,True),
               ("quarantined",2,2,"correct_revision",True,True,True), ("active",2,2,"change_policy",True,False,True),
               ("tombstoned",2,2,"restore",True,True,False), ("active",True,1,"forget",True,True,True),
               ("active",2,2,"forget",1,True,True)]
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(ValueError): api.govern_transition(*case)

    def test_required_check_missing(self):
        self.assertEqual(api.aggregate_checks(["C01"], [{"id":"C02","status":"PASS"}]), "NOT_RUN")
        self.assertEqual(api.aggregate_checks(["C01"], [{"id":"C01","status":"PASS"}]), "PASS")
        self.assertEqual(api.aggregate_checks(["C01"], [{"id":"C01","status":"NOT_RUN"}]), "NOT_RUN")
        self.assertEqual(api.aggregate_checks(["C01"], [{"id":"C02","status":"FAIL"}]), "FAIL")
        for required,checks in (([],[]), (["C01","C01"],[]), (["fake"],[]), (["C01"],[{"id":"fake","status":"PASS"}]), (["C01"],[{"id":"C01","status":"PASS"}]*2)):
            with self.assertRaises(ValueError): api.aggregate_checks(required, checks)

    def test_schema_unknown_keyword_fails_closed(self):
        schema = api.load_schema(); schema["oneOf"][0]["properties"]["content"]["format"] = "email"
        with patch.object(api,"load_schema",return_value=schema):
            with self.assertRaises(ValueError): api.validate_request(create())

    def test_schema_misplaced_keyword_fails_closed(self):
        schema = api.load_schema(); schema["oneOf"][0]["properties"]["content"]["minimum"] = 10
        with patch.object(api, "load_schema", return_value=schema):
            with self.assertRaises(ValueError): api.validate_request(create())

    def test_retry_full_truth_table(self):
        expected = {
            ("unknown", False, False): "query_only", ("unknown", False, True): "query_only",
            ("unknown", True, False): "query_only", ("unknown", True, True): "query_only",
            ("committed", False, False): "query_only", ("committed", False, True): "conflict",
            ("committed", True, False): "query_only", ("committed", True, True): "return_original",
            ("absent", False, False): "query_only", ("absent", False, True): "conflict",
            ("absent", True, False): "query_only", ("absent", True, True): "eligible_for_authorized_first_apply"}
        for args, result in expected.items():
            with self.subTest(args=args): self.assertEqual(api.retry_action(*args), result)

    def test_aggregation_priority_and_optional(self):
        self.assertEqual(api.aggregate_checks(["C01"], [{"id":"C02", "status":"FAIL"}]), "FAIL")
        self.assertEqual(api.aggregate_checks(["C01"], [{"id":"C01", "status":"PASS"}, {"id":"C02", "status":"NOT_RUN"}]), "PASS")
        self.assertEqual(api.aggregate_checks(["C01", "R01"], [{"id":"C01", "status":"PASS"}]), "NOT_RUN")
        self.assertEqual(api.aggregate_checks(["C01"], [{"id":"C01", "status":"NOT_RUN"}, {"id":"C02", "status":"FAIL"}]), "FAIL")

    def test_depth_and_node_budget_direct(self):
        deep = "x"
        for i in range(26): deep = [deep]
        with self.assertRaises(ValueError): api.validate_request(deep)
        with self.assertRaises(ValueError): api.validate_request([None] * 10001)

    def test_schema_single_snapshot(self):
        with patch.object(api,"load_schema",wraps=api.load_schema) as load:
            api.validate_request(create())
            self.assertEqual(load.call_count,1)


if __name__ == "__main__": unittest.main()
