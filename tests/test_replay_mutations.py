import importlib.util
import pathlib
import tempfile
import unittest
import io
from sandbox_runtime import replay
from framework.spec import ROOT

MUTANTS=[
 ("skip_task_binding",'if event["task_sha"]!=expected_task:','if False:'),
 ("forget_stream",'if event["stream"]!=self.stream or event["session"]!=self.session:','if False:'),
 ("forget_session",' or event["session"]!=self.session',''),
 ("skip_collision",'if self.seen[eid]!=sha:','if False:'),
 ("skip_order",'elif seq!=self.seq+1:','elif False:'),
 ("skip_resume_binding",'if self.task is None or digest(value)!=digest(self.task):','if self.task is None:'),
 ("skip_bootstrap",'if self.task is None and digest(value)!=self.bootstrap_sha:','if False:'),
 ("skip_revision",'if value["revision"]<=self.revisions.get(value["id"],0):','if False:'),
 ("reset_budget_on_prepare",'self._clear();self.work=copy.deepcopy(self.task)','self._clear();self.spent={"calls":0,"bytes":0};self.work=copy.deepcopy(self.task)'),
 ("skip_spent_bytes",'for k in self.spent:self.spent[k]+=','for k in ("calls",):self.spent[k]+='),
 ("skip_clear",'self.controller.invalidate();self.ticket=None;self.work=None','pass'),
]

class ReplayMutationTests(unittest.TestCase):
 def test_independent_replay_suite_kills_all(self):
    original=pathlib.Path(replay.__file__).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
      for i,(name,old,new) in enumerate(MUTANTS):
        with self.subTest(name=name):
          count=2 if name=="skip_spent_bytes" else 1;self.assertEqual(original.count(old),count)
          p=pathlib.Path(tmp)/("mut%d.py"%i);p.write_text(original.replace(old,new),encoding="utf-8")
          s=importlib.util.spec_from_file_location("_replay_mutant",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
          s=importlib.util.spec_from_file_location("_replay_checks",ROOT/"tests/test_replay.py");t=importlib.util.module_from_spec(s);s.loader.exec_module(t);t.Replay=m.Replay
          result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(t))
          self.assertFalse(result.wasSuccessful(),name+" survived")
