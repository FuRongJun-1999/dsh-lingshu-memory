"""Mutation killers for unified Condition Space and BiTemporal evaluators."""
import importlib.util
import io
import pathlib
import tempfile
import unittest
from framework import conditions
from framework.spec import ROOT

MUTANTS = [
    ("default_required_slots_empty", "required_slots: tuple[str, ...] = SLOTS", "required_slots: tuple[str, ...] = ()"),
    ("allow_empty_required_slots", "or not required_slots ", ""),
    ("unknown_equals_match", "saw_defer = True", "pass"),
    ("missing_attr_satisfies", 'if k not in rec["attributes"]:\n            saw_defer = True', 'if k not in rec["attributes"]:\n            pass'),
    ("contradiction_lost_to_defer", 'if r_s["text"] != q_s["text"]:\n                return "NO_MATCH"', 'if r_s["text"] != q_s["text"]:\n                saw_defer = True'),
    ("fabricate_declared_slot", '"carrier": {"state": "unknown"}', '"carrier": {"state": "declared", "text": "default"}'),
    ("dual_axis_no_match_lost", 'if verdict == "NO_MATCH":\n            return "NO_MATCH"', 'if verdict == "NO_MATCH":\n            saw_defer = True'),
    ("dual_axis_defer_ignored", 'if verdict == "DEFER":\n            saw_defer = True', 'if verdict == "DEFER":\n            pass'),
]


class ConditionMutationTests(unittest.TestCase):
    def test_independent_suite_kills_all_mutants(self):
        original = pathlib.Path(conditions.__file__).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            for idx, (name, old, new) in enumerate(MUTANTS):
                with self.subTest(name=name):
                    self.assertIn(old, original, "anchor missing: " + name)
                    path = pathlib.Path(tmp) / ("cond_mutant_%d.py" % idx)
                    path.write_text(original.replace(old, new, 1), encoding="utf-8")
                    spec = importlib.util.spec_from_file_location("_cond_mutant", path)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    ts = importlib.util.spec_from_file_location("_cond_tests", ROOT / "tests/test_conditions.py")
                    tm = importlib.util.module_from_spec(ts)
                    ts.loader.exec_module(tm)
                    tm.c = mod
                    result = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(tm))
                    self.assertFalse(result.wasSuccessful(), "mutant survived: " + name)


if __name__ == "__main__":
    unittest.main()
