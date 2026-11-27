import inspect
import unittest
from framework import propagation_preview as mod
from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from test_read_edges import request
from test_shadow_runtime import bitemp, cspace, ctx

SHA='1'*64


def loc(key,rev=1):return key,rev,SHA


def options(**kw):
    public=frozenset({'alice','bob'});private=frozenset({'alice'})
    nodes={k:Node('t1',1,SHA,1,acl,acl) for k,acl in [('root',public),('mid',public),('end',public),('hidden',private)]}
    m=dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()))
    return dict(dict(context=ctx('bob'),now=10,view=ReadSnapshot(1,1,nodes,dict.fromkeys(nodes,m)),model=Model(),budget=8,
                     states={loc('root'):'expired',loc('mid'):'doubted',loc('end'):'verified'},
                     downstream={loc('root'):(loc('mid'),),loc('mid'):(loc('root'),loc('end'))}),**kw)


class PropagationTests(unittest.TestCase):
    def test_passes_doubted_without_marking_and_handles_cycle(self):
        out=mod.preview_propagation(request('root'),**options())
        self.assertEqual(out['planned'],[dict(id='end',revision=1,content_sha=SHA)])
        self.assertFalse(out['applied'])
        text=inspect.getsource(mod); old='            work.append(ref)'; env={}
        self.assertEqual(text.count(old),1)
        exec(compile(text.replace(old,"            if state!='doubted': work.append(ref)",1),'<propagation-relay-mutant>','exec'),env)
        self.assertEqual(env['preview_propagation'](request('root'),**options())['planned'],[])

    def test_hidden_or_stale_intermediates_are_not_traversed(self):
        for mid in (loc('hidden'),loc('mid',2)):
            downstream={loc('root'):(mid,),mid:(loc('end'),)}
            self.assertEqual(mod.preview_propagation(request('root'),**options(downstream=downstream))['planned'],[])
        self.assertEqual(mod.preview_propagation(request('hidden'),**options()),{'error':'NOT_FOUND_OR_DENIED'})

    def test_no_partial_plan_on_budget_or_unknown_state(self):
        self.assertEqual(mod.preview_propagation(request('root'),**options(budget=2)),{'error':'PROPAGATION_BUDGET'})
        self.assertEqual(mod.preview_propagation(request('root'),**options(states={loc('root'):'expired'})),{'error':'PROPAGATION_STATE_UNKNOWN'})
        self.assertEqual(mod.preview_propagation(request('root'),**options(states={})),{'error':'PROPAGATION_ROOT_UNCONFIRMED'})
