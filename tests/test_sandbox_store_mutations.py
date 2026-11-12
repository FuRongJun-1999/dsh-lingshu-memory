import importlib.util
import io
import pathlib
import tempfile
import unittest
from sandbox_runtime import store
from framework.spec import ROOT

MUTANTS=[
 ("skip_auth",'return self._model.can_read(key,self._nodes,tenant=ctx["tenant"],principal=ctx["principal"],clearance=ctx["clearance"])','return True'),
 ("ignore_digest",' or n.content_sha!=locator["content_sha"]',''),
 ("implicit_isolation",'if synthetic is not True or type(probe) is not Probe:','if type(probe) is not Probe:'),
 ("limit_before_auth",'visible=[key for key in ids if self._allowed(key,ctx)]','visible=[key for key in sorted(ids)[:limit] if self._allowed(key,ctx)]'),
 ("retain_fixture_alias",'row=copy.deepcopy(original)','row=original'),
 ("retain_return_alias",'row=copy.deepcopy(self._records[key])','row=self._records[key]'),
]

class StoreMutationTests(unittest.TestCase):
 def test_independent_store_suite_kills_each(self):
    original=pathlib.Path(store.__file__).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
      for i,(name,old,new) in enumerate(MUTANTS):
        with self.subTest(name=name):
          self.assertEqual(original.count(old),1)
          path=pathlib.Path(tmp)/("store_mutant_%d.py"%i);path.write_text(original.replace(old,new),encoding="utf-8")
          spec=importlib.util.spec_from_file_location("_store_mutant",path)
          module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
          ts=importlib.util.spec_from_file_location("_store_checks",ROOT/"tests/test_sandbox_store.py")
          checks=importlib.util.module_from_spec(ts);ts.loader.exec_module(checks)
          checks.SyntheticStore=module.SyntheticStore;checks.Probe=module.Probe
          result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(checks))
          self.assertFalse(result.wasSuccessful(),name+" survived")
