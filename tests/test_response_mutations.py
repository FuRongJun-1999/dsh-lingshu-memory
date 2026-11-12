"""Response mutants must fail an independent expected-value assertion."""
import importlib.util
import io
import pathlib
import tempfile
import unittest
from framework import responses
from framework.spec import ROOT

MUTANTS=[
 ("cancel_without_seal", 'if sealed_cancel: return ("absent", "cancelled", "return_original_cancel")', 'if True: return ("absent", "cancelled", "return_original_cancel")'),
 ("committed_cancelled", 'if state in ("committed", "rejected"):', 'if state == "rejected":'),
 ("replay_without_authorization", 'if not authorized: return (None, None, "authenticate")', 'if False: return (None, None, "authenticate")'),
 ("partial_history_accept", 'if conflict or not complete or not matching or state == "unknown":', 'if conflict or not matching or state == "unknown":'),
 ("content_scope_leak", 'projection if content_allowed and status == "committed" else "unknown"', 'projection if status == "committed" else "unknown"'),
 ("conflict_negative_fresh", 'sum((rejected, cancelled, fresh)) != 1', 'sum((rejected, cancelled, fresh)) == 0'),
]

class ResponseMutationTests(unittest.TestCase):
 def test_independent_suite_kills_mutants(self):
    original=pathlib.Path(responses.__file__).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
      for i,(name,old,new) in enumerate(MUTANTS):
       with self.subTest(name=name):
        self.assertIn(old,original)
        path=pathlib.Path(tmp)/("response_mutant_"+str(i)+".py");path.write_text(original.replace(old,new),encoding="utf-8")
        spec=importlib.util.spec_from_file_location("_response_mutant",path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.ROOT=ROOT
        ts=importlib.util.spec_from_file_location("_response_mutant_tests",ROOT/"tests/test_responses.py");tm=importlib.util.module_from_spec(ts);ts.loader.exec_module(tm);tm.m=module
        result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(tm))
        self.assertGreater(result.testsRun,10);self.assertGreater(len(result.failures),0,"survived: "+name)

 def test_cancelled_token_cannot_regain_apply(self):
    from framework import api
    original=pathlib.Path(api.__file__).read_text(encoding="utf-8")
    old='if negative_basis == "durable_cancel": return "return_original_cancel"'
    self.assertIn(old,original)
    with tempfile.TemporaryDirectory() as tmp:
      path=pathlib.Path(tmp)/"api_cancel_mutant.py"
      path.write_text(original.replace(old,'if negative_basis == "durable_cancel": return "eligible_for_authorized_first_apply"'),encoding="utf-8")
      spec=importlib.util.spec_from_file_location("_api_cancel_mutant",path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.ROOT=ROOT
      ts=importlib.util.spec_from_file_location("_cancel_tests",ROOT/"tests/test_responses.py");tm=importlib.util.module_from_spec(ts);ts.loader.exec_module(tm);tm.api=module
      result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(tm))
      self.assertGreater(len(result.failures),0,"cancelled token replay mutant survived")

if __name__ == "__main__": unittest.main()
