import json
import os
import subprocess
import sys
import unittest
from framework.spec import ROOT
from test_sandbox_store import record, context
from test_sandbox_controller import task
from test_replay import event

class ReplayCliTests(unittest.TestCase):
 def invoke(self,events,**kwargs):
    v=dict(fixture=[record()],context=context(),now=1,bootstrap_task=task(),stream="stream-a",session="session-a",events=events);v.update(kwargs)
    return subprocess.run([sys.executable,"-X","utf8","-B","-m","sandbox_runtime.replay_cli","--synthetic"],input=json.dumps(v),cwd=ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace",env=dict(os.environ,PYTHONUTF8="1",PYTHONDONTWRITEBYTECODE="1"),shell=False,timeout=15)
 def test_actual_process_compact_resume_and_duplicate(self):
    es=[event(1,"task/start",dict(task=task())),event(2,"system-prompt/assemble"),event(3,"context/compact"),event(4,"session/resume",dict(task=task())),event(5,"decision"),event(5,"decision")]
    p=self.invoke(es);self.assertEqual(p.returncode,0,p.stderr);r=json.loads(p.stdout)
    self.assertEqual([x["status"] for x in r["results"]],["started","prepared","compacted","prepared","ready","duplicate"])
    self.assertEqual(r["spent"],dict(calls=9,bytes=95));self.assertEqual(len(r["actions"]),9)
    self.assertEqual(r["results"][-1],{"status":"duplicate"})
 def test_actual_process_out_of_order_never_outputs_fact(self):
    p=self.invoke([event(1,"task/start",dict(task=task())),event(2,"system-prompt/assemble"),event(4,"decision"),event(5,"decision")])
    self.assertEqual(p.returncode,3);r=json.loads(p.stdout)
    self.assertEqual(r["results"][-1],{"status":"blocked","reason":"DESYNC"})
    self.assertNotIn("body",p.stdout);self.assertNotIn("citation",p.stdout)
 def test_untrusted_bootstrap_mismatch_and_old_stream(self):
    p=self.invoke([event(1,"task/start",dict(task=task()))],bootstrap_task=task(revision=2))
    self.assertEqual(p.returncode,3);self.assertEqual(json.loads(p.stdout)["results"],[{"status":"blocked","reason":"BOOTSTRAP_MISMATCH"}])
    p=self.invoke([event(1,"decision",stream="old")]);self.assertEqual(p.returncode,3)
 def test_closed_input_no_paths_and_bounded_event_count(self):
    self.assertEqual(self.invoke([],path="not-allowed").returncode,2)
    self.assertEqual(self.invoke([event(1,"decision")]*257).returncode,2)
