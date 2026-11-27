import importlib.util
import io
import pathlib
import tempfile
import unittest
from sandbox_runtime import controller
from framework import context_recall
from framework.spec import ROOT

RECALL_MUTANTS = {"skip_emit_read", "ignore_ambiguity", "ignore_version", "ignore_conditions"}

MUTANTS=[
 ("context_rebind",' or ctx!=state["context"]',''),
 ("task_rebind",'if digest(task_shape(task))!=state["task_sha"]:','if False:'),
 ("skip_emit_read","current = get(old['locator'])",'current=copy.deepcopy(old)'),
 ("ignore_ambiguity",'if len(found) > 1:','if False:'),
 ("ignore_byte_budget",'if state["bytes"]>state["task"]["budget"]["bytes"]:','if False:'),
 ("ignore_call_budget",'if state["calls"]>=state["task"]["budget"]["calls"]:','if False:'),
 ("ignore_fresh_trace",'if observed!=[expected]:','if False:'),
 ("ignore_prior_trace",'if self.probe.events[state["trace_start"]:]!=state["trace"]:','if False:'),
 ("ignore_alert_effect",'if self.alerts.events[before:]!=[{"event":"alert","reason":reason}]:','if False:'),
 ("ignore_version",'("key","architecture","version","conditions")','("key","architecture","conditions")'),
 ("ignore_conditions",'("key","architecture","version","conditions")','("key","architecture","version")'),
 ("reuse_ticket",'_,state=self._pending;self._pending=None','_,state=self._pending'),
]

class ControllerMutationTests(unittest.TestCase):
 def test_independent_suite_kills_every_mutant(self):
    original=pathlib.Path(controller.__file__).read_text(encoding="utf-8")
    recall_source=pathlib.Path(context_recall.__file__).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
      for i,(name,old,new) in enumerate(MUTANTS):
        with self.subTest(name=name):
          if name in RECALL_MUTANTS:
              self.assertEqual(recall_source.count(old), 1)
              import types
              mutated = types.ModuleType('_recall_mutant')
              exec(compile(recall_source.replace(old,new,1), context_recall.__file__, 'exec'), mutated.__dict__)
              module = types.ModuleType('_controller_using_mutant')
              exec(compile(original, controller.__file__, 'exec'), module.__dict__)
              module.select_evidence = mutated.select_evidence
              module.revalidate_evidence = mutated.revalidate_evidence
              module.Halt = mutated.RecallBlocked
          else:
              self.assertEqual(original.count(old),1)
              path=pathlib.Path(tmp)/("controller_mutant_%d.py"%i);path.write_text(original.replace(old,new),encoding="utf-8")
              spec=importlib.util.spec_from_file_location("_controller_mutant",path)
              module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
          ts=importlib.util.spec_from_file_location("_controller_checks",ROOT/"tests/test_sandbox_controller.py")
          checks=importlib.util.module_from_spec(ts);ts.loader.exec_module(checks)
          checks.Controller=module.Controller;checks.AlertSink=module.AlertSink;checks.Ticket=module.Ticket
          result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(checks))
          self.assertFalse(result.wasSuccessful(),name+" survived")
