import importlib.util
import pathlib
import tempfile
import unittest
import copy
from framework.spec import ROOT,parse
from sandbox_runtime import benchmark

MUTANTS=[
 ("ignore_evidence",'if output.get("records")!=[{"body":body,"citation":loc}]:','if False:'),
 ("ignore_alert",'if alerts!=[{"event":"alert","reason":expected["reason"]}]:','if False:'),
 ("ignore_blocked_facts",'if output!={"status":"blocked","reason":expected["reason"]}:','if False:'),
 ("ignore_actions",'if projection!=case["expected_actions"]:','if False:'),
 ("ignore_fixture",'if sha(rows)!=case["fixture_sha"]:','if False:'),
 ("ignore_trace",'if sha(actions)!=case["expected_trace_sha"]:','if False:'),
 ("ignore_text",'if actual_ids!=case["text_top4"]:','if False:'),
]

class BenchmarkMutationTests(unittest.TestCase):
 def test_each_evaluator_mutant_rejected_by_independent_negative(self):
    original=pathlib.Path(benchmark.__file__).read_text(encoding="utf-8");manifest=parse((ROOT/"spec/benchmark_cases.json").read_text(encoding="utf-8"))
    positive=manifest["cases"][0];negative=next(c for c in manifest["cases"] if c["variant"]=="missing")
    ready=benchmark.run_case(positive);blocked=benchmark.run_case(negative)
    with tempfile.TemporaryDirectory() as tmp:
      for i,(name,old,new) in enumerate(MUTANTS):
        with self.subTest(name=name):
          self.assertEqual(original.count(old),1);p=pathlib.Path(tmp)/("bench%d.py"%i);p.write_text(original.replace(old,new),encoding="utf-8")
          s=importlib.util.spec_from_file_location("_bench_mutant",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
          if name=="ignore_evidence":
            out=copy.deepcopy(ready["output"]);out["records"][0]["body"]="fake";err=m.assess(positive,out,ready["actions"],[]);key="evidence"
          elif name=="ignore_alert":err=m.assess(negative,blocked["output"],blocked["actions"],[]);key="alert"
          elif name=="ignore_blocked_facts":err=m.assess(negative,dict(blocked["output"],records=[{"body":"fake"}]),blocked["actions"],blocked["alerts"]);key="blocked_shape"
          elif name=="ignore_actions":err=m.assess(positive,ready["output"],ready["actions"][:-1],[]);key="action_oracle"
          elif name=="ignore_trace":
            actions=copy.deepcopy(ready["actions"]);actions[-1]["result_sha"]="0"*64;err=m.assess(positive,ready["output"],actions,[]);key="trace_oracle"
          else:
            c=copy.deepcopy(positive);key="fixture_drift" if name=="ignore_fixture" else "lexical_oracle";c["fixture_sha" if name=="ignore_fixture" else "text_top4"]="0"*64 if name=="ignore_fixture" else ["wrong"]
            err=m.run_case(c)["errors"]
          # Replay the identical fault on the original: false-positive controls matter.
          if name in ("ignore_evidence","ignore_alert","ignore_blocked_facts","ignore_actions","ignore_trace"):
            args=([positive,out,ready["actions"],[]] if name=="ignore_evidence" else [negative,blocked["output"],blocked["actions"],[]] if name=="ignore_alert" else [negative,dict(blocked["output"],records=[{"body":"fake"}]),blocked["actions"],blocked["alerts"]] if name=="ignore_blocked_facts" else [positive,ready["output"],ready["actions"][:-1],[]] if name=="ignore_actions" else [positive,ready["output"],actions,[]])
            self.assertIn(key,benchmark.assess(*args))
          else:self.assertIn(key,benchmark.run_case(c)["errors"])
          self.assertNotIn(key,err)
