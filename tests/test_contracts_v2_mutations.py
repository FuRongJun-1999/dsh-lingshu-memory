"""Mutation killers for unified v2 contracts."""
import importlib.util
import io
import pathlib
import tempfile
import unittest
from framework import contracts
from framework.spec import ROOT

MUTANTS = [
    ("allow_conflicting_attr_key", 'if k in attrs:\n            raise ValueError("CONFLICTING_CONDITION")', "pass"),
    ("allow_read_target", 'if target is not None:\n            raise ValueError("INVALID_ENVELOPE: target forbidden on read")', "pass"),
    ("allow_records_on_non_read", 'if scope != "read" or outcome != "ok":', 'if outcome != "ok":'),
    ("allow_records_on_non_ok_read", 'if scope != "read" or outcome != "ok":', 'if scope != "read":'),
    ("allow_receipt_on_read", 'if receipt is not None and scope not in ("mutation", "receipt"):', 'if False:'),
    ("skip_body_sha_check", 'if rec["body_sha"] != expected_sha or rec["locator"]["content_sha"] != expected_sha:', "if False:"),
    ("allow_bidi_build", "if contains_spoofing_controls(body):", "if False:"),
    ("allow_bidi_validate", 'if contains_spoofing_controls(rec["body"]):', "if False:"),
    ("allow_alm_061c", "[0x061C]", "[]"),
    ("allow_cancel_committed", 'target["commit_status"] != "absent"', "False"),
    ("skip_denied_disclosure_guard", 'if code == "NOT_FOUND_OR_DENIED" and (records is not None or target is not None or receipt is not None):', "if False:"),
]


class ContractsV2MutationTests(unittest.TestCase):
    def test_independent_suite_kills_all_mutants(self):
        original = pathlib.Path(contracts.__file__).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            for idx, (name, old, new) in enumerate(MUTANTS):
                with self.subTest(name=name):
                    self.assertIn(old, original, "anchor missing: " + name)
                    path = pathlib.Path(tmp) / ("ct_mutant_%d.py" % idx)
                    path.write_text(original.replace(old, new, 1), encoding="utf-8")
                    spec = importlib.util.spec_from_file_location("_ct_mutant", path)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    ts = importlib.util.spec_from_file_location("_ct_tests", ROOT / "tests/test_contracts_v2.py")
                    tm = importlib.util.module_from_spec(ts)
                    ts.loader.exec_module(tm)
                    tm.ct = mod
                    result = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(tm))
                    self.assertFalse(result.wasSuccessful(), "mutant survived: " + name)


if __name__ == "__main__":
    unittest.main()
