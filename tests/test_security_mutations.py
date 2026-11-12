import importlib.util
import io
import pathlib
import tempfile
import unittest
from framework import security
from framework.spec import ROOT

MUTANTS=[
 ("binding_not_compared",'if a!=b: return False','if False: return False'),
 ("clearance_not_bound",'if a!=b: return False','a["context"]["clearance"]=b["context"]["clearance"]\n    if a!=b: return False'),
 ("expiry_inclusive",'now<a["snapshot"]["expires_at"]','now<=a["snapshot"]["expires_at"]'),
 ("cursor_not_validated",'or not cursor_validated: return False',': return False'),
 ("hold_bypass",'e["authorized"] is not True or e["legal_hold"] is not False','e["authorized"] is not True'),
 ("terminal_deleted",'if e["kind"]=="token_final": return "retain"','if False: return "retain"'),
 ("recovery_dependency_ignored",'("commit_resolved","terminal_durable","dependencies_closed")','("commit_resolved","terminal_durable")'),
 ("active_purge",'("active","quarantined")','("quarantined",)'),
 ("audit_obligation_ignored",'if e["kind"]=="audit" and e["audit_closed"] is not True: return "retain"','if False: return "retain"')]

class SecurityMutationTests(unittest.TestCase):
 def test_independent_suite_kills_each(self):
    src=pathlib.Path(security.__file__).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
      for i,(name,old,new) in enumerate(MUTANTS):
       with self.subTest(name=name):
        self.assertEqual(src.count(old),1)
        path=pathlib.Path(tmp)/("security_mutant_"+str(i)+".py");path.write_text(src.replace(old,new),encoding="utf-8")
        spec=importlib.util.spec_from_file_location("_security_mutant",path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        spec=importlib.util.spec_from_file_location("_security_tests",ROOT/"tests/test_security.py");tm=importlib.util.module_from_spec(spec);spec.loader.exec_module(tm);tm.s=module
        result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(tm))
        self.assertGreaterEqual(result.testsRun,9);self.assertGreater(len(result.failures),0,"survived "+name)
if __name__=="__main__":unittest.main()
