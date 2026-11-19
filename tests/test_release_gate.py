import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from scripts.release_gate import ROOT, evaluate


class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); self.dir=Path(tmp.name)
        self.doc=json.loads((ROOT/'spec/acceptance.status.json').read_text(encoding='utf-8'))
        self.candidate='a'*40; self.doc['candidate']=self.candidate
        for ident,item in self.doc['items'].items():
            run={'argv':['fixture-test',ident],'output':'synthetic observation','exit_code':0}
            artifact=dict(id=ident,candidate=self.candidate,scope=('specification' if ident[0]=='C' else 'production-power' if ident=='R04' else 'production'),data_sha='b'*64,policy_sha='d'*64,producer='fixture-runner',reviewer='fixture-reviewer',runs={'baseline':run,'injected':dict(run,exit_code=1),'restored':run})
            item.update(state='PASS',evidence_sha=self.store(artifact))

    def store(self, artifact):
        raw=json.dumps(artifact,sort_keys=True).encode(); key=hashlib.sha256(raw).hexdigest(); (self.dir/(key+'.json')).write_bytes(raw); return key

    def test_population_and_profile_policy_are_not_self_declared(self):
        self.assertEqual(evaluate(self.doc,self.dir)['power']['state'],'ELIGIBLE')
        d=copy.deepcopy(self.doc); d['items'].pop('R02')
        with self.assertRaises(ValueError): evaluate(d,self.dir)
        d=copy.deepcopy(self.doc); d['items']['R01']['required_for']=[]
        with self.assertRaises(ValueError): evaluate(d,self.dir)
        self.doc['items']['R04'].update(state='NOT_RUN',evidence_sha=None)
        result=evaluate(self.doc,self.dir); self.assertEqual(result['production']['state'],'ELIGIBLE'); self.assertEqual(result['power']['missing_pass'],['R04'])
        self.doc['release_markers']=['power']
        with self.assertRaises(ValueError): evaluate(self.doc,self.dir)

    def test_evidence_binding_and_paired_control(self):
        item=self.doc['items']['R01']; key=item['evidence_sha']; path=self.dir/(key+'.json'); raw=path.read_bytes(); original=json.loads(raw)
        for patch in ({'id':'R02'},{'candidate':'e'*40},{'scope':'shadow'},{'reviewer':'fixture-runner'},{'policy_sha':'?'},{'runs':dict(original['runs'],injected=original['runs']['baseline'])}):
            with self.subTest(field=next(iter(patch))):
                item['evidence_sha']=self.store(dict(original,**patch))
                with self.assertRaises(ValueError): evaluate(self.doc,self.dir)
        item['evidence_sha']=key
        with self.assertRaises(ValueError): evaluate(self.doc,self.dir,expected_candidate='e'*40)
        path.write_bytes(raw+b' ')
        with self.assertRaises(ValueError): evaluate(self.doc,self.dir)
        path.unlink()
        with self.assertRaises(OSError): evaluate(self.doc,self.dir)

    def test_cli_distinguishes_blocked_invalid_and_eligible(self):
        def invoke(*args):
            return subprocess.run([sys.executable,'-X','utf8','-B','scripts/release_gate.py',*args],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',env=dict(os.environ,PYTHONUTF8='1'),shell=False,timeout=15)
        q=invoke('--profile','production','--candidate',self.candidate)
        self.assertEqual(q.returncode,3,q.stderr); self.assertEqual(len(json.loads(q.stdout)['production']['missing_pass']),18)
        doc=self.dir/'register.json'; doc.write_text(json.dumps(self.doc),encoding='utf-8')
        args=['--status',str(doc),'--evidence-dir',str(self.dir),'--profile','power','--candidate',self.candidate]
        q=invoke(*args); self.assertEqual(q.returncode,0,q.stderr); self.assertEqual(json.loads(q.stdout)['power']['state'],'ELIGIBLE')
        self.doc['items']['R05'].update(state='FAIL',evidence_sha=None);self.doc['release_markers']=['power'];doc.write_text(json.dumps(self.doc),encoding='utf-8'); self.assertEqual(invoke(*args).returncode,2)
