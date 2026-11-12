import copy
import json
import os
import subprocess
import sys
import unittest
from framework.spec import ROOT,parse
from sandbox_runtime.acceptance import audited,validate_demos,CHECKS

class AuditFixtures(unittest.TestCase):
 def check_empty(self):pass
 @unittest.skip("not executed")
 def check_skip(self):self.assertTrue(True)
 @unittest.expectedFailure
 def check_expected(self):self.assertTrue(False)
 def check_assertion_not_executed(self):
    if False:self.assertTrue(True)
 def check_failed(self):self.assertTrue(False)
 def check_real(self):self.assertTrue(True)

class AcceptanceTests(unittest.TestCase):
 def test_empty_skipped_expected_failure_and_unexecuted_assertion_rejected(self):
    for name in ("empty","skip","expected","assertion_not_executed","failed"):
      self.assertFalse(audited(AuditFixtures("check_"+name))["passed"],name)
    self.assertTrue(audited(AuditFixtures("check_real"))["passed"])
 def test_actual_complete_acceptance_process_matches_report(self):
    p=subprocess.run([sys.executable,"-X","utf8","-B","scripts/context_acceptance.py"],cwd=ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace",env=dict(os.environ,PYTHONUTF8="1",PYTHONDONTWRITEBYTECODE="1"),shell=False,timeout=120)
    self.assertEqual(p.returncode,0,p.stderr);report=json.loads(p.stdout)
    self.assertEqual(report["verdict"],"ISOLATED_ACCEPTED");self.assertEqual(len(report["checks"]),22)
    self.assertEqual(report["production"],"NOT_RUN");self.assertEqual(report["gui_integration"],"NOT_RUN")
 def test_duplicate_mapping_cannot_fake_obligation_coverage(self):
    self.assertEqual(len(CHECKS),22);self.assertEqual(len(set(CHECKS.values())),22)
 def test_demo_validator_rejects_ready_without_actual_calls_and_wrong_locator(self):
    from sandbox_runtime.cli import execute
    from sandbox_runtime.replay_cli import execute as replay
    c=execute(parse((ROOT/"spec/context_demo.json").read_text(encoding="utf-8")));r=replay(parse((ROOT/"spec/replay_demo.json").read_text(encoding="utf-8")));b=parse((ROOT/"spec/benchmark_result.json").read_text(encoding="utf-8"))
    self.assertTrue(validate_demos(c,r,b))
    for field in ("actions","output"):
      bad=copy.deepcopy(c)
      if field=="actions":bad[field]=[]
      else:bad[field]["records"][0]["citation"]["id"]="wrong"
      with self.assertRaises(ValueError):validate_demos(bad,r,b)
    bad=copy.deepcopy(r);bad["results"][-1]=bad["results"][4]
    with self.assertRaises(ValueError):validate_demos(c,bad,b)

 def test_parent_rejects_skips_failures_fake_ok_and_noninteger_counts(self):
    from sandbox_runtime.acceptance import validate_child
    good=dict(passed=True,tests=1,assertions=1,skips=0,expected_failures=0,failures=0,errors=0)
    validate_child(good)
    for k,v in [("passed",False),("passed","true"),("tests",0),("tests",True),("assertions",0),("skips",1),("expected_failures",1),("failures",1),("errors",1)]:
      with self.assertRaises(ValueError):validate_child(dict(good,**{k:v}))
 def test_coverage_and_snapshot_drift_rejected(self):
    from sandbox_runtime.acceptance import validate_coverage,validate_snapshot
    contract=parse((ROOT/"spec/context_loop.json").read_text(encoding="utf-8"));bad=dict(CHECKS);bad["filter_before_limit"]=bad["task_bound_retrieval"]
    with self.assertRaises(ValueError):validate_coverage(contract,bad)
    stored=parse((ROOT/"spec/context_acceptance.json").read_text(encoding="utf-8"));bad=copy.deepcopy(stored);bad["sources"]["sandbox_runtime/controller.py"]="0"*64
    with self.assertRaises(ValueError):validate_snapshot(bad,stored)
