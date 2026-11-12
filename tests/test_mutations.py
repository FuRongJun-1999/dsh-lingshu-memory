"""Mutate isolated model modules; independent tests must fail for each mutant."""
import importlib.util
import io
import pathlib
import sys
import tempfile
import unittest
from framework import model
from framework.spec import ROOT

MUTANTS = [
    ("formation_quantifier", 'if any(e.relation == rule["relation"] for e in edges)', 'if all(e.relation == rule["relation"] for e in edges)'),
    ("clearance_direction", 'clearance >= d.sensitivity', 'clearance <= d.sensitivity'),
    ("dangling_evidence_skip", 'if target is None or target.tombstoned:', 'if e.relation == "derived" and (target is None or target.tombstoned):'),
    ("empty_disk_absent", 'return RecoveryResult("unknown", "missing", False)', 'return RecoveryResult("absent", "missing", False)'),
    ("identity_self_proof", 'verifier_id != source_id', 'verifier_id == source_id'),
    ("acl_union", 'readers &= sub.readers', 'readers |= sub.readers'),
    ("forget_releases_history", 'self.projection[key] = "tombstoned"', 'self.projection[key] = "tombstoned"; self.history.pop(key)'),
]

class MutationTests(unittest.TestCase):
    def test_independent_suite_kills_model_mutants(self):
        original = pathlib.Path(model.__file__).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            for index, (name, old, new) in enumerate(MUTANTS):
                with self.subTest(name=name):
                    self.assertIn(old, original, "mutation anchor missing")
                    mutated = original.replace(old, new)
                    self.assertNotEqual(original, mutated)
                    path = pathlib.Path(tmp) / ("mutant_" + str(index) + ".py")
                    path.write_text(mutated, encoding="utf-8")
                    module_name = "framework._mutant_" + str(index)
                    spec = importlib.util.spec_from_file_location(module_name, path)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    # Load the same independent expected-value suite against the mutant.
                    test_spec = importlib.util.spec_from_file_location("_mutant_tests", ROOT / "tests/test_model.py")
                    test_module = importlib.util.module_from_spec(test_spec)
                    test_spec.loader.exec_module(test_module)
                    for attr in ("Model", "Node", "Edge", "RecoveryEvidence", "recover", "TokenHistory", "request_fingerprint", "verification_eligible"):
                        setattr(test_module, attr, getattr(module, attr))
                    suite = unittest.defaultTestLoader.loadTestsFromModule(test_module)
                    result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
                    self.assertGreater(result.testsRun, 20)
                    self.assertFalse(result.wasSuccessful(), "mutant survived: " + name)
                    sys.modules.pop(module_name, None)

if __name__ == "__main__":
    unittest.main()
