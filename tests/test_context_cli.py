import json
import os
import subprocess
import sys
import unittest
from framework.spec import ROOT
from test_sandbox_store import record, context
from test_sandbox_controller import task

class ContextCliTests(unittest.TestCase):
 def invoke(self,raw,args=None):
    return subprocess.run([sys.executable,"-X","utf8","-B","-m","sandbox_runtime.cli",*(args if args is not None else ["--synthetic"])],input=raw,cwd=ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace",env=dict(os.environ,PYTHONUTF8="1",PYTHONDONTWRITEBYTECODE="1"),shell=False,timeout=15)
 def test_real_subprocess_runs_retrieval_readback_and_output(self):
    envelope=dict(fixture=[record()],context=context(),now=1,task=task())
    p=self.invoke(json.dumps(envelope));self.assertEqual(p.returncode,0,p.stderr)
    result=json.loads(p.stdout);self.assertEqual(result["output"]["status"],"ready")
    self.assertEqual(result["output"]["records"][0]["body"],"blue widget limit 8")
    self.assertEqual([x["operation"] for x in result["actions"]],["search","get","search","get","get"])
 def test_missing_evidence_has_real_alert_and_no_records(self):
    p=self.invoke(json.dumps(dict(fixture=[],context=context(),now=1,task=task())))
    self.assertEqual(p.returncode,3);v=json.loads(p.stdout)
    self.assertEqual(v["output"],{"status":"blocked","reason":"EVIDENCE_GAP"})
    self.assertEqual(v["alerts"],[{"event":"alert","reason":"EVIDENCE_GAP"}])
 def test_no_implicit_mode_duplicate_keys_paths_or_oversize(self):
    self.assertNotEqual(self.invoke("{}",args=[]).returncode,0)
    for raw in ['{"fixture":[],"fixture":[]}',json.dumps({"path":"not-a-fixture"}),"x"*131073]:
      p=self.invoke(raw);self.assertEqual(p.returncode,2)
      self.assertEqual(json.loads(p.stdout),{"output":{"status":"blocked","reason":"INVALID_INPUT"}})
