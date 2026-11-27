import inspect
import unittest
from framework import read_lineage as mod
from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Edge, Model, Node
from framework.read_get import ReadSnapshot
from test_read_edges import request
from test_shadow_runtime import bitemp, cspace, ctx

SHA='1'*64
KEY=('child',1,SHA)


def args(bindings):
    public=frozenset({'alice','bob'}); private=frozenset({'alice'})
    nodes={k:Node('t1',1,SHA,1,acl,acl) for k,acl in [('a',public),('b',public),('hidden',private)]}
    nodes['child']=Node('t1',1,SHA,1,public,public,(Edge('b','derived',1,SHA),))
    meta=dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()))
    return dict(relation='split_from',limit=1,context=ctx('bob'),now=10,view=ReadSnapshot(1,1,nodes,dict.fromkeys(nodes,meta)),
                model=Model(),bindings=bindings)


class ReadLineageTests(unittest.TestCase):
    def test_exact_explicit_relation_sorted_after_filtering(self):
        entries=(('split_from','hidden',1,SHA),('split_from','b',1,SHA),('split_from','a',1,SHA),('merged_from','b',1,SHA))
        result=mod.read_lineage(request('child'),**args({KEY:entries}))
        self.assertEqual(result['relations'],[dict(relation='split_from',parent=dict(id='a',revision=1,content_sha=SHA))])
        self.assertEqual(mod.read_lineage(request('child'),**args({}))['relations'],[])

    def test_stale_child_or_parent_and_missing_auth(self):
        records=(('split_from','b',2,SHA),)
        result=mod.read_lineage(request('child'),**args({KEY:records}))
        self.assertEqual(result['relations'],[])
        self.assertEqual(mod.read_lineage(request('child'),**args({('child',2,SHA):records}))['relations'],[])
        self.assertEqual(mod.read_lineage(request('hidden'),**args({})),{'error':'NOT_FOUND_OR_DENIED'})
        src=inspect.getsource(mod);guard=" or (parent['revision'],parent['content_sha'])!=(revision,sha)"
        self.assertEqual(src.count(guard),1);scope={}
        exec(compile(src.replace(guard,'',1),'<lineage-revision-mutant>','exec'),scope)
        self.assertEqual(scope['read_lineage'](request('child'),**args({KEY:records}))['relations'][0]['parent']['id'],'b')

    def test_over_budget_returns_no_partial_spectrum(self):
        self.assertEqual(mod.read_lineage(request('child'),**args({KEY:(('split_from','a',1,SHA),)*129})),{'error':'LINEAGE_BUDGET'})
