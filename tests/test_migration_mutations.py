import importlib.util
import io
import pathlib
import tempfile
import unittest
from framework import migration
from framework.spec import ROOT

MUTANTS=[
 ("end_inclusive",'p>=b[1]','p>b[1]'),
 ("unknown_matches",'if a[0]=="unknown" or b[0]=="unknown": return "DEFER"','if False: return "DEFER"'),
 ("axis_fallback",'interval(value[axis])','interval(value["observed"])'),
 ("unsafe_read_only",'if any(available.get(x) is False for x in read_required): return "reject"','if any(available.get(x) is False for x in read_required): return "read_only"'),
 ("unknown_capability",'if any(available.get(x) is not True for x in read_required): return "defer"','if False: return "defer"'),
 ("capsule_hash_bypass",'if legacy_capsule(raw)!=value:','if False:'),
 ("known_contradiction_lost",'if b[0]=="instant" and p>=b[1]: return "NO_MATCH"','if b[0]=="instant" and a[0]!="unknown" and p>=b[1]: return "NO_MATCH"')]

class MigrationMutationTests(unittest.TestCase):
 def test_independent_suite_kills_each(self):
    src=pathlib.Path(migration.__file__).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
      for i,(name,old,new) in enumerate(MUTANTS):
       with self.subTest(name=name):
        self.assertIn(old,src)
        path=pathlib.Path(tmp)/("migration_mutant_"+str(i)+".py");path.write_text(src.replace(old,new),encoding="utf-8")
        spec=importlib.util.spec_from_file_location("_migration_mutant",path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.ROOT=ROOT
        spec=importlib.util.spec_from_file_location("_migration_tests",ROOT/"tests/test_migration.py");tm=importlib.util.module_from_spec(spec);spec.loader.exec_module(tm);tm.m=module
        result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(tm))
        self.assertGreater(result.testsRun,6);self.assertGreater(len(result.failures),0,"survived "+name)

if __name__ == "__main__":unittest.main()
