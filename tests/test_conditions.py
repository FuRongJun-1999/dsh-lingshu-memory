"""Independent expected tests for unified Condition Space and BiTemporal contracts."""
import copy
import unittest
from framework import conditions as c
from framework.spec import ROOT, digest, load, parse, validate
from scripts.spec_tools import freeze_errors

A = "2024-01-01T00:00:00Z"
B = "2024-01-01T00:00:01Z"
C = "2024-01-01T00:00:02Z"
UNK = {"state": "unknown"}
INF = {"state": "unbounded"}


def decl(text):
    return {"state": "declared", "text": text}


def cond(carrier=None, method=None, existence=None, attrs=None):
    return {
        "carrier": copy.deepcopy(carrier or UNK),
        "method": copy.deepcopy(method or UNK),
        "existence": copy.deepcopy(existence or UNK),
        "attributes": copy.deepcopy(attrs if attrs is not None else {}),
    }


def tbundle(obs_start=INF, obs_end=INF, eff_start=UNK, eff_end=UNK):
    return {
        "observed": {"start": copy.deepcopy(obs_start), "end": copy.deepcopy(obs_end)},
        "effective": {"start": copy.deepcopy(eff_start), "end": copy.deepcopy(eff_end)},
    }


def at(v):
    return {"state": "instant", "value": v}


class UnifiedConditionTests(unittest.TestCase):
    def test_unknown_equals_unknown_never_matches_by_default(self):
        all_unk = cond()
        self.assertEqual(c.condition_match(all_unk, all_unk), "DEFER")
        with self.assertRaises(ValueError):
            c.condition_match(all_unk, all_unk, required_slots=())
        r = cond(carrier=UNK, method=decl("m1"), existence=decl("e1"), attrs={"env": "prod"})
        q = cond(carrier=UNK, method=decl("m1"), existence=decl("e1"), attrs={"env": "prod"})
        self.assertEqual(c.condition_match(r, q), "DEFER")

    def test_declared_slot_with_unknown_counterpart_defers(self):
        r_decl = cond(carrier=decl("c1"), method=decl("m1"), existence=decl("e1"))
        q_unk = cond(carrier=UNK, method=decl("m1"), existence=decl("e1"))
        self.assertEqual(c.condition_match(r_decl, q_unk), "DEFER")
        self.assertEqual(c.condition_match(q_unk, r_decl), "DEFER")

    def test_contradiction_precedes_defer(self):
        r = cond(carrier=UNK, method=decl("m1"), existence=decl("e1"), attrs={"region": "west"})
        q = cond(carrier=UNK, method=decl("m1"), existence=decl("e1"), attrs={"region": "east"})
        self.assertEqual(c.condition_match(r, q, required_slots=("carrier",)), "NO_MATCH")
        r_slot = cond(carrier=decl("email"), method=UNK, existence=decl("e1"))
        q_slot = cond(carrier=decl("sms"), method=UNK, existence=decl("e1"))
        self.assertEqual(c.condition_match(r_slot, q_slot, required_slots=("method",)), "NO_MATCH")

    def test_missing_attribute_defers_not_satisfies(self):
        r = cond(carrier=decl("c1"), method=decl("m1"), existence=decl("e1"), attrs={})
        q = cond(carrier=decl("c1"), method=decl("m1"), existence=decl("e1"), attrs={"region": "east"})
        self.assertEqual(c.condition_match(r, q), "DEFER")

    def test_exact_declared_match(self):
        r = cond(carrier=decl("c1"), method=decl("m1"), existence=decl("e1"), attrs={"region": "east", "tier": "1"})
        q = cond(carrier=decl("c1"), method=decl("m1"), existence=decl("e1"), attrs={"region": "east"})
        self.assertEqual(c.condition_match(r, q), "MATCH")

    def test_normalize_legacy_never_fabricates_declared(self):
        n1 = c.normalize_conditions(["region=east", "tier=1"])
        n2 = c.normalize_conditions({"region": "east", "tier": "1"})
        self.assertEqual(n1, n2)
        self.assertEqual(n1["carrier"], UNK)
        self.assertEqual(n1["method"], UNK)
        self.assertEqual(n1["existence"], UNK)
        self.assertEqual(n1["attributes"], {"region": "east", "tier": "1"})
        self.assertEqual(c.condition_match(n1, n2), "DEFER")

    def test_normalize_rejects_malformed_and_conflicting_inputs(self):
        for bad in (["no_equals"], ["=val"], ["k="], ["k=1", "k=2"], "k=1", {"": "v"}, {"k": 1}, ["a=b"] * 33):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    c.normalize_conditions(bad)


class BiTemporalTests(unittest.TestCase):
    def test_explicit_axis_required_and_no_fallback(self):
        b = tbundle(obs_start=at(A), obs_end=at(C), eff_start=UNK, eff_end=UNK)
        for bad_q in ({}, {"other": A}, None, []):
            with self.assertRaises(ValueError):
                c.bitemporal_match(b, bad_q)
        self.assertEqual(c.bitemporal_match(b, {"observed": B}), "MATCH")
        self.assertEqual(c.bitemporal_match(b, {"effective": B}), "DEFER")
        self.assertEqual(c.bitemporal_match(b, {"observed": B, "effective": B}), "DEFER")

    def test_dual_axis_contradiction_beats_defer(self):
        b = tbundle(obs_start=at(A), obs_end=at(B), eff_start=UNK, eff_end=UNK)
        self.assertEqual(c.bitemporal_match(b, {"observed": B, "effective": A}), "NO_MATCH")

    def test_bitemporal_strict_precision_half_open_and_unknown_vs_unbounded(self):
        b = tbundle(obs_start=at(A), obs_end=at(B), eff_start=INF, eff_end=INF)
        self.assertEqual(c.bitemporal_match(b, {"observed": A, "effective": C}), "MATCH")
        self.assertEqual(c.bitemporal_match(b, {"observed": B, "effective": A}), "NO_MATCH")
        b_unk = tbundle(obs_start=UNK, obs_end=INF, eff_start=INF, eff_end=INF)
        self.assertEqual(c.bitemporal_match(b_unk, {"observed": A}), "DEFER")
        for bad_ts in ("2024-01-01T00:00:00+00:00", "2024-01-01T00:00:00.5Z", "2024-02-30T00:00:00Z", 1704067200):
            with self.subTest(bad_ts=bad_ts):
                with self.assertRaises(ValueError):
                    c.bitemporal_match(b, {"observed": bad_ts})


class Core020SpecTests(unittest.TestCase):
    def test_actual_lock_matches_core_and_links_previous_010(self):
        base = load()
        lock = parse((ROOT / "spec/contract.lock.json").read_text(encoding="utf-8"))
        self.assertEqual(freeze_errors(base, lock), [])
        self.assertEqual(lock["spec_version"], "0.2.0")
        self.assertEqual(lock["sha256"], digest(base))
        self.assertEqual(lock["previous_sha256"], "0b73148ae2bddf3a94dd544aa6f9f0387ed43091e298e9c67fe337a2ae986740")

    def test_core_020_new_section_mutations_fail(self):
        base = load()
        self.assertEqual(base["spec_version"], "0.2.0")
        lock = dict(spec_version=base["spec_version"], sha256=digest(base), previous_sha256=None, reason="fixture")
        for section, key, value in (
            ("conditions", "unknown_equals_match", True),
            ("conditions", "missing_equals_satisfied", True),
            ("bitemporal", "no_axis_fallback", False),
            ("bitemporal", "unknown_is_unbounded", True),
            ("bitemporal", "interval", "closed"),
        ):
            s = copy.deepcopy(base)
            s[section][key] = value
            self.assertIn("full spec digest drift", freeze_errors(s, lock))
            with self.assertRaises(ValueError):
                validate(s)


if __name__ == "__main__":
    unittest.main()
