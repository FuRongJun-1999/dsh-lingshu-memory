import inspect
import tempfile
import unittest

from framework import time_consistency as time_check
from framework.migration import instant
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from shadow_runtime.time_check_port import file_time_check
from test_shadow_runtime import ShadowMarkdownStore, cspace, ctx, write_req
from test_time_relation import span

POINT = '2024-01-05T00:00:00Z'


class TimeConsistencyTests(unittest.TestCase):
    def test_contradictions_precede_unknown_and_mutation_accepts_right_endpoint(self):
        p = instant(POINT)
        expected = [(span(2,8),('consistent',None)),(span(4,4),('conflict','empty_interval')),
                    (span(8,2),('conflict','inverted_interval')), (None,('conflict','invalid_interval')),
                    (span('unknown',5),('conflict','outside_interval')),
                    (span('unknown',8),('unknown','unknown_bound')),
                    (span('unbounded','unbounded'),('consistent',None))]
        for bounds, result in expected:
            self.assertEqual(time_check.diagnose_time(bounds,p),result)
        text=inspect.getsource(time_check); guard='point >= right[1]'
        self.assertEqual(text.count(guard),1)
        mutant={};exec(compile(text.replace(guard,'point > right[1]',1),'<time-check-mutant>','exec'),mutant)
        self.assertEqual(time_check.diagnose_time(span(2,5),p),('conflict','outside_interval'))
        self.assertEqual(mutant['diagnose_time'](span(2,5),p),('consistent',None))

    def test_hidden_and_missing_are_indistinguishable_without_metadata(self):
        owner=frozenset({'alice'});node=Node('t1',1,'1'*64,1,owner,owner)
        args=dict(node_id='hidden',axis='observed',point=POINT,condition_query=cspace(),context=ctx('bob'),now=10,model=Model())
        for nodes in ({'hidden':node}, {}):
            self.assertEqual(time_check.check_time(view=ReadSnapshot(1,1,nodes,{}),**args),{'error':'NOT_FOUND_OR_DENIED'})

    def test_file_current_revision_and_explicit_axis(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=ShadowMarkdownStore(tmp,synthetic=True)
            req=dict(write_req('initial','synthetic fixture'),bitemporal=dict(observed=span(1,5),effective=span(2,8)))
            self.assertEqual(store.execute(req,ctx(),10)['outcome'],'ok')
            def run(axis, query=None):
                return file_time_check(ShadowMarkdownStore(tmp,synthetic=True),node_id='node-1',axis=axis,point=POINT,
                                       condition_query=query or cspace(),context=ctx(),now=30)
            self.assertEqual(run('observed')['reason'],'outside_interval')
            good=run('effective')
            self.assertEqual((good['status'],set(good)),('consistent',{'status','reason','axis','locator'}))
            self.assertEqual(run('effective',dict(cspace(),method={'state':'unknown'})),{'error':'CONDITION_DEFERRED'})
            changed=dict(req,kind='Write.modify',node_id='node-1',expected_revision=1,caller_token='revision',
                         content='revised fixture',bitemporal=dict(observed=span(1,5),effective=span('unknown',8)))
            self.assertEqual(store.execute(changed,ctx(),20)['outcome'],'ok')
            actual=run('effective')
            self.assertEqual((actual['status'],actual['reason'],actual['locator']['revision']),('unknown','unknown_bound',2))
