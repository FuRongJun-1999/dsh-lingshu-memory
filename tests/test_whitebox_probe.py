import hashlib
import inspect
import unittest
from dataclasses import replace
from unittest.mock import Mock
from framework import whitebox_probe as mod
from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from test_read_edges import request
from test_shadow_runtime import bitemp, cspace, ctx

TEXT='合成核验文本'
SHA=hashlib.sha256(TEXT.encode()).hexdigest()


def options(**overrides):
    readers=frozenset({'alice'}); node=Node('t1',1,SHA,1,readers,readers)
    meta=dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()))
    view=ReadSnapshot(1,1,{'probe':node},{'probe':meta})
    return dict(dict(expected_revision=1,expected_sha=SHA,context=ctx(),now=10,request_id='probe',
                     snapshot=lambda:view,body=lambda *_:TEXT,model=Model(),current_context=ctx,current_now=lambda:11),**overrides)


class WhiteboxProbeTests(unittest.TestCase):
    def test_verified_receipt_has_no_text(self):
        self.assertEqual(mod.verify_existing(request('probe'),**options()),
                         dict(status='verified_readback',locator=dict(id='probe',revision=1,content_sha=SHA)))

    def test_denial_and_revocation_cannot_pass(self):
        body=Mock(return_value=TEXT)
        self.assertEqual(mod.verify_existing(request('probe'),**options(context=ctx('bob'),body=body)),
                         dict(status='unverified',reason='NOT_FOUND_OR_DENIED'))
        body.assert_not_called()
        opt=options(body=body); view=opt['snapshot'](); node=view.nodes['probe']
        snapshots=iter((view,replace(view,nodes={'probe':replace(node,current_readers=frozenset())})))
        opt['snapshot']=lambda:next(snapshots)
        self.assertEqual(mod.verify_existing(request('probe'),**opt),dict(status='unverified',reason='POLICY_CHANGED'))

    def test_nonempty_reply_is_not_enough_and_guard_mutant(self):
        kw=options(expected_revision=2)
        self.assertEqual(mod.verify_existing(request('probe'),**kw),dict(status='unverified',reason='PROBE_MISMATCH'))
        self.assertEqual(mod.verify_existing(request('probe'),**options(body=lambda *_:'other'))['reason'],'INTEGRITY_FAILURE')
        src=inspect.getsource(mod);needle="row['locator']!=expected or ";ns={}
        self.assertEqual(src.count(needle),1)
        exec(compile(src.replace(needle,'',1),'<whitebox-revision-mutant>','exec'),ns)
        self.assertEqual(ns['verify_existing'](request('probe'),**kw)['status'],'verified_readback')
