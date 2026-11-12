import copy
import importlib.util
import pathlib
import tempfile
import unittest
from framework.spec import ROOT,parse
from sandbox_runtime import acceptance

MUTANTS=[
 ("ignore_child_failure",'if result["tests"]!=1 or result["assertions"]<1 or any(result[k]!=0 for k in ("skips","expected_failures","failures","errors")):','if False:'),
 ("ignore_report_drift",'if actual!=stored:','if False:'),
 ("ignore_context_body",'if context["output"]!={"status":"ready","task_sha":sha(fixture["task"]),"records":expected}:','if False:'),
 ("ignore_context_calls",'if [a["operation"] for a in context["actions"]]!=["search","get","search","get","get"] or context["alerts"]:','if False:'),
 ("ignore_replay_duplicate",'if replay["results"][4]["records"]!=expected or replay["results"][-1]!={"status":"duplicate"}:','if False:'),
]

class AcceptanceMutationTests(unittest.TestCase):
 def test_each_negative_detected_original_and_missed_mutant(self):
    from sandbox_runtime.cli import execute
    from sandbox_runtime.replay_cli import execute as replay
    original=pathlib.Path(acceptance.__file__).read_text(encoding="utf-8")
    c=execute(parse((ROOT/"spec/context_demo.json").read_text(encoding="utf-8")));r=replay(parse((ROOT/"spec/replay_demo.json").read_text(encoding="utf-8")));b=parse((ROOT/"spec/benchmark_result.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
      for i,(name,old,new) in enumerate(MUTANTS):
        with self.subTest(name=name):
          self.assertEqual(original.count(old),1);p=pathlib.Path(tmp)/("accept%d.py"%i);p.write_text(original.replace(old,new),encoding="utf-8")
          s=importlib.util.spec_from_file_location("_accept_mutant",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
          if name=="ignore_child_failure":fn="validate_child";args=[dict(passed=True,tests=1,assertions=1,skips=1,expected_failures=0,failures=0,errors=0)]
          elif name=="ignore_report_drift":fn="validate_snapshot";args=[dict(verdict="ISOLATED_ACCEPTED",sources={}),dict(verdict="ISOLATED_ACCEPTED",sources={"x":"sha"})]
          else:
            cc=copy.deepcopy(c);rr=copy.deepcopy(r);fn="validate_demos"
            if name=="ignore_context_body":cc["output"]["records"][0]["body"]="fabricated"
            elif name=="ignore_context_calls":cc["actions"]=[]
            else:rr["results"][-1]=dict(status="duplicate",records=rr["results"][4]["records"])
            args=[cc,rr,b]
          with self.assertRaises(ValueError):getattr(acceptance,fn)(*args)
          getattr(m,fn)(*args)
