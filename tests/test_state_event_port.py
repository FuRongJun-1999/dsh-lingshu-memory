import inspect
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from framework.spec import ROOT
from shadow_runtime import state_event_port as event_port
from test_shadow_runtime import ctx


def args(**changes):
    return dict(dict(subject='fixture',slot='phase',context=ctx(),now=10,allowed=lambda *_:True),**changes)


class StateEventPortTests(unittest.TestCase):
    def test_reopen_and_stale_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=event_port.StateEventStore(tmp,synthetic=True)
            b=event_port.StateEventStore(tmp,synthetic=True)
            empty=a.inspect(**args())['checkpoint']
            first=a.append(**args(),expected=empty,old=None,new='ready')['checkpoint']
            self.assertEqual(b.append(**args(),expected=empty,old='ready',new='wrong'),{'error':'STATE_CHANGED'})
            self.assertEqual(b.inspect(**args())['value'],'ready')
            self.assertEqual(b.append(**args(now=11),expected=first,old='ready',new=None)['status'],'appended')
            self.assertEqual(a.inspect(**args(now=12))['status'],'retired')
            self.assertEqual(a.inspect(**args(context=ctx(tenant='other'),now=12))['status'],'empty')

    def test_denial_and_failed_replace_do_not_change_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=event_port.StateEventStore(tmp,synthetic=True)
            no=args(allowed=lambda *_:False)
            self.assertEqual(store.append(**no,expected=None,old=None,new='ready'),{'error':'NOT_FOUND_OR_DENIED'})
            self.assertFalse(store.root.exists())
            empty=store.inspect(**args())['checkpoint']
            before=store.append(**args(),expected=empty,old=None,new='ready')['checkpoint']
            with patch.object(event_port,'atomic_write_text',side_effect=OSError('synthetic I/O failure')):
                with self.assertRaises(OSError):store.append(**args(now=11),expected=before,old='ready',new='changed')
            self.assertEqual(store.inspect(**args(now=11))['value'],'ready')
            p, = Path(store.root).glob('*.json');p.write_bytes(b'{')
            self.assertEqual(store.inspect(**args(now=11)),{'error':'CHAIN_CONFLICT'})

    def test_stale_checkpoint_mutation_is_observable(self):
        body=inspect.getsource(event_port)
        old="if expected != head or current.get('value') != old:"
        self.assertEqual(body.count(old),1)
        mutant={};exec(compile(body.replace(old,"if current.get('value') != old:",1),'<head-conflict-mutant>','exec'),mutant)
        for cls, result in ((event_port.StateEventStore,{'error':'STATE_CHANGED'}),(mutant['StateEventStore'],None)):
            with tempfile.TemporaryDirectory() as tmp:
                store=cls(tmp,synthetic=True);empty=store.inspect(**args())['checkpoint']
                store.append(**args(),expected=empty,old=None,new='ready')
                outcome=store.append(**args(),expected=empty,old='ready',new='wrong')
                if result:self.assertEqual(outcome,result)
                else:self.assertEqual(outcome['status'],'appended')

    def test_two_processes_competing_for_one_checkpoint(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            script = """
import json, sys
from shadow_runtime.state_event_port import StateEventStore, EMPTY
ctx=dict(tenant='t1',principal='alice',clearance=2,auth_epoch=1,policy_generation=1,expires_at=1000)
s=StateEventStore(sys.argv[1],synthetic=True)
print(json.dumps(s.append(subject='fixture',slot='phase',context=ctx,now=10,allowed=lambda *_:True,
                          expected=EMPTY,old=None,new=sys.argv[2])))
"""
            procs=[subprocess.Popen([sys.executable,'-B','-c',script,tmp,value],cwd=ROOT,shell=False,
                                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
                   for value in ('a','b')]
            try:
                replies=[]
                for p in procs:
                    out,err=p.communicate(timeout=15)
                    self.assertEqual(p.returncode,0,err)
                    replies.append(json.loads(out))
                self.assertEqual(sum(x.get('status')=='appended' for x in replies),1)
                self.assertEqual(sum(x.get('error')=='STATE_CHANGED' for x in replies),1)
                got=event_port.StateEventStore(tmp,synthetic=True).inspect(**args())
                self.assertEqual(got['seq'],1);self.assertIn(got['value'],('a','b'))
            finally:
                for p in procs:
                    if p.poll() is None:p.kill();p.communicate(timeout=5)
