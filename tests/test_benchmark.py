import copy
import json
import os
import subprocess
import sys
import unittest
from framework.spec import ROOT,parse
from sandbox_runtime.benchmark import run,run_case,assess,sha

class BenchmarkTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
    cls.manifest=parse((ROOT/"spec/benchmark_cases.json").read_text(encoding="utf-8"));cls.report=run(cls.manifest)
 def test_fixed_oracle_and_full_actual_matrix(self):
    self.assertEqual(sha(self.manifest),parse((ROOT/"spec/benchmark.lock.json").read_text(encoding="utf-8"))["manifest_sha"])
    self.assertEqual(self.report["passed"],self.report["total"])
    self.assertEqual(self.report["total"],39)
 def test_lexical_and_keyed_and_passive_are_separate(self):
    groups=self.report["groups"];self.assertEqual(len(groups),12)
    for g in groups:
      self.assertEqual(g["keyed_ready"],2);self.assertEqual(g["passive_evidence"],0)
      expect=2 if g["query"]!="unrelatedphrase" and g["noise"]==0 else 0
      self.assertEqual(g["text_target_hits"],expect)
    self.assertEqual(self.report["llm_evaluation"],"NOT_RUN")
 def test_repeat_deterministic_and_shuffle_independent(self):
    c=self.manifest["cases"][0];self.assertEqual(run_case(c),run_case(c))
    for g in self.report["groups"]:
      rs=[r for r in self.report["cases"] if r["variant"]=="normal" and r["query"]==g["query"] and r["noise"]==g["noise"]]
      self.assertEqual(rs[0]["output"],rs[1]["output"] | {"task_sha":rs[0]["output"]["task_sha"]})
 def test_wrong_body_locator_and_missing_alert_cannot_pass(self):
    c=self.manifest["cases"][0];r=run_case(c)
    for field,value in [("body","fabricated"),("citation",dict(id="wrong",revision=1,content_sha="0"*64))]:
      out=copy.deepcopy(r["output"]);out["records"][0][field]=value
      self.assertIn("evidence",assess(c,out,r["actions"],r["alerts"]))
    c=next(c for c in self.manifest["cases"] if c["variant"]=="missing");r=run_case(c)
    self.assertIn("alert",assess(c,r["output"],r["actions"],[]))
    out=dict(r["output"],records=[{"body":"leak"}]);self.assertIn("blocked_shape",assess(c,out,r["actions"],r["alerts"]))
 def test_claimed_ready_without_work_does_not_pass(self):
    c=self.manifest["cases"][0];r=run_case(c)
    self.assertIn("no_actual_call",assess(c,r["output"],[],[]))
 def test_actual_benchmark_process(self):
    p=subprocess.run([sys.executable,"-X","utf8","-B","scripts/context_benchmark.py"],cwd=ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace",env=dict(os.environ,PYTHONUTF8="1",PYTHONDONTWRITEBYTECODE="1"),shell=False,timeout=90)
    self.assertEqual(p.returncode,0,p.stderr);r=json.loads(p.stdout);self.assertEqual(r["transcript_sha"],self.report["transcript_sha"])
    stored=parse((ROOT/"spec/benchmark_result.json").read_text(encoding="utf-8"));self.assertEqual(r,stored)

 def test_dummy_search_and_missing_final_read_do_not_pass(self):
    c=self.manifest["cases"][0];r=run_case(c)
    self.assertIn("action_oracle",assess(c,r["output"],[dict(operation="search",returned=1,mode="text")],[]))
    self.assertIn("action_oracle",assess(c,r["output"],r["actions"][:-1],[]))
 def test_generator_drift_and_text_oracle_are_not_self_fulfilling(self):
    c=copy.deepcopy(self.manifest["cases"][0]);c["fixture_sha"]="0"*64
    self.assertIn("fixture_drift",run_case(c)["errors"])
    c=copy.deepcopy(self.manifest["cases"][0]);c["text_top4"]=["wrong"]
    self.assertIn("lexical_oracle",run_case(c)["errors"])

 def test_same_counts_but_forged_trace_digest_cannot_pass(self):
    c=self.manifest["cases"][0];r=run_case(c);actions=copy.deepcopy(r["actions"])
    actions[-1]["result_sha"]="0"*64
    self.assertIn("trace_oracle",assess(c,r["output"],actions,[]))
 def test_false_positive_evaluator_control_checks_real_original(self):
    c=self.manifest["cases"][0];r=run_case(c)
    self.assertEqual(assess(c,r["output"],r["actions"],[]),[])
