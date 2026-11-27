import inspect
import unittest
from unittest.mock import Mock
from framework import promotion_preview as mod
from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from test_read_edges import request
from test_shadow_runtime import bitemp, cspace, ctx

KEY=('n',1,'1'*64)


def row(**kw):
    return dict(dict(key=KEY,layer='contextual',complete=True,locked=False,hits=2,importance_bp=5000),**kw)


def options(**kw):
    acl=frozenset({'alice'}); node=Node('t1',1,KEY[2],1,acl,acl)
    meta=dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()))
    return dict(dict(context=ctx(),now=10,view=ReadSnapshot(1,1,{'n':node},{'n':meta}),model=Model(),
             can_plan=lambda _:True,evidence=lambda _:row(),min_hits=2,min_importance_bp=6000),**kw)


class PromotionPreviewTests(unittest.TestCase):
    def test_two_thresholds_and_plan_only(self):
        expected=dict(status='candidate',locator=dict(id='n',revision=1,content_sha=KEY[2]),target_layer='knowledge',applied=False)
        self.assertEqual(mod.preview_promotion(request('n'),**options()),expected)
        self.assertEqual(mod.preview_promotion(request('n'),**options(evidence=lambda _:row(hits=0,importance_bp=6000))),expected)
        for proof in (row(hits=1),row(locked=True),row(complete=False),row(layer='knowledge')):
            self.assertEqual(mod.preview_promotion(request('n'),**options(evidence=lambda _:proof)),{'status':'not_eligible'})

    def test_explicit_grant_and_visibility_precede_evidence(self):
        read=Mock()
        self.assertEqual(mod.preview_promotion(request('n'),**options(context=ctx('bob'),evidence=read)),{'error':'NOT_FOUND_OR_DENIED'})
        self.assertEqual(mod.preview_promotion(request('n'),**options(can_plan=lambda _:False,evidence=read)),{'error':'PROMOTION_DENIED'})
        read.assert_not_called()

    def test_stale_evidence_and_binding_mutant(self):
        kw=options(evidence=lambda _:row(key=('n',2,KEY[2])))
        self.assertEqual(mod.preview_promotion(request('n'),**kw),{'error':'PROMOTION_EVIDENCE_UNKNOWN'})
        source=inspect.getsource(mod);guard=" or row['key']!=key";ns={}
        self.assertEqual(source.count(guard),1)
        exec(compile(source.replace(guard,'',1),'<promotion-revision-mutant>','exec'),ns)
        self.assertEqual(ns['preview_promotion'](request('n'),**kw)['status'],'candidate')
