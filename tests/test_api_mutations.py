"""Kill API predicate mutants with the independent expected-value suite."""
import importlib.util
import io
import pathlib
import tempfile
import unittest
from framework import api
from framework.spec import ROOT

MUTANTS = [
    ("cursor_kind", 'if a != b: return False', 'if field != "read_kind" and a != b: return False'),
    ("cursor_policy", 'if a != b: return False', 'if field != "policy_generation" and a != b: return False'),
    ("unknown_replay", 'if not history_complete or commit_status == "unknown": return "query_only"', 'if not history_complete: return "query_only"'),
    ("govern_cas", 'if current_revision != expected_revision: raise ValueError("REVISION_CONFLICT")', 'if False: raise ValueError("REVISION_CONFLICT")'),
    ("govern_restore_proof", 'if action == "restore" and not proof_fresh:', 'if False:'),
    ("missing_check_pass", 'seen.get(key, "NOT_RUN")', 'seen.get(key, "PASS")'),
    ("scope_principal", 'and values == record_scope', 'and values[0] == record_scope[0] and values[2:] == record_scope[2:]'),
]

class ApiMutationTests(unittest.TestCase):
    def test_independent_suite_kills_mutants(self):
        original=pathlib.Path(api.__file__).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            for i,(name,old,new) in enumerate(MUTANTS):
                with self.subTest(name=name):
                    self.assertIn(old,original)
                    path=pathlib.Path(tmp)/("api_mutant_"+str(i)+".py")
                    path.write_text(original.replace(old,new),encoding="utf-8")
                    spec=importlib.util.spec_from_file_location("_api_mutant",path)
                    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                    module.ROOT=ROOT
                    ts=importlib.util.spec_from_file_location("_api_mutant_tests",ROOT/"tests/test_api.py")
                    tm=importlib.util.module_from_spec(ts);ts.loader.exec_module(tm);tm.api=module
                    result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(tm))
                    self.assertGreater(result.testsRun,15)
                    self.assertGreater(len(result.failures),0,"mutant not caught by assertion: "+name)

if __name__ == "__main__": unittest.main()
