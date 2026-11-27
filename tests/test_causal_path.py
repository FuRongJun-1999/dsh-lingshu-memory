import inspect
import unittest
from framework import causal_path as mod
from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from test_read_edges import request
from test_shadow_runtime import bitemp, cspace, ctx

SHA='1'*64


def loc(key, rev=1):return key,rev,SHA


def call(bindings, *, hidden=False, depth=3):
    public=frozenset(('alice','bob'))
    def node(key):
        acl=frozenset(('alice',)) if key=='middle' and hidden else public
        return Node('t1',1,SHA,1,acl,acl)
    nodes={k:node(k) for k in ('start','middle','end')}
    meta=dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()))
    view=ReadSnapshot(1,1,nodes,dict.fromkeys(nodes,meta))
    return mod.conditional_path(request('start'),target='end',depth=depth,context=ctx('bob'),now=10,
                                view=view,model=Model(),bindings=bindings)


class CausalPathTests(unittest.TestCase):
    def test_visible_shortest_chain_and_cycle(self):
        bindings={loc('start'):(loc('middle'),),loc('middle'):(loc('start'),loc('end'))}
        self.assertEqual(call(bindings,depth=1),{'status':'no_visible_path'})
        self.assertEqual([x['id'] for x in call(bindings)['path']],['start','middle','end'])
        self.assertEqual(call({}),{'status':'no_visible_path'})

    def test_hidden_and_stale_intermediates_yield_no_path(self):
        bindings={loc('start'):(loc('middle'),),loc('middle'):(loc('end'),)}
        self.assertEqual(call(bindings,hidden=True),{'status':'no_visible_path'})
        bindings[loc('start')]=(loc('middle',2),)
        self.assertEqual(call(bindings),{'status':'no_visible_path'})
        blob=inspect.getsource(mod); anchor='            if current is None or current!=candidate:'
        self.assertEqual(blob.count(anchor),1)
        variant={};exec(compile(blob.replace(anchor,'            if current is None:',1),'<path-revision-mutant>','exec'),variant)
        from unittest.mock import patch
        with patch.object(mod,'conditional_path',variant['conditional_path']):
            self.assertEqual(call(bindings)['status'],'visible_path')

    def test_budget_does_not_claim_absence(self):
        bindings={loc('start'):(loc('missing'),)*513+(loc('end'),)}
        self.assertEqual(call(bindings),{'error':'PATH_BUDGET'})
