import inspect
import tempfile
import unittest

from framework import time_relation
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from shadow_runtime.relation_port import file_time_relation
from test_shadow_runtime import ShadowMarkdownStore, cspace, ctx, write_req


def span(start,end):
    def bound(n):
        return dict(state=n) if isinstance(n,str) else dict(state='instant',value=f'2024-01-{n:02}T00:00:00Z')
    return dict(start=bound(start),end=bound(end))


class TimeRelationTests(unittest.TestCase):
    def test_half_open_and_unknown_relations(self):
        a=span(2,5)
        for b, expected in [(span(5,9),'before'),(span(1,2),'after'),(span(2,5),'equals'),(span(2,3),'contains'),
                            (span(1,5),'during'),(span(4,7),'overlaps'),(span(2,2),'empty'),
                            (span('unknown',5),'unknown'),(span('unbounded','unbounded'),'during')]:
            with self.subTest(expected=expected):
                self.assertEqual(time_relation.classify(a,b),expected)
        source=inspect.getsource(time_relation)
        anchor='if y <= z:'
        self.assertEqual(source.count(anchor),1)
        mutant={}
        exec(compile(source.replace(anchor,'if y < z:',1),'<time-boundary-mutant>','exec'),mutant)
        self.assertEqual(mutant['classify'](a,span(5,9)),'overlaps')

    def test_hidden_and_absent_endpoint_are_identical_without_reading_metadata(self):
        alice=frozenset({'alice'}); both=frozenset({'alice','bob'})
        a=Node('t1',1,'1'*64,1,both,both)
        b=Node('t1',1,'2'*64,1,alice,alice)
        class Tripwire(dict):
            def __getitem__(self,key):
                raise AssertionError('unauthorized metadata read')
        for nodes in ({'a':a,'b':b},{'a':a}):
            actual=time_relation.relate_time(a='a',b='b',axis='observed',condition_query=cspace(),
                 context=ctx('bob'),now=20,view=ReadSnapshot(1,1,nodes,Tripwire()),model=Model())
            self.assertEqual(actual,{'error':'NOT_FOUND_OR_DENIED'})

    def test_file_comparison_is_axis_specific_and_uses_current_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=ShadowMarkdownStore(tmp,synthetic=True)
            a=dict(write_req('alpha','alpha',readers=('alice','bob')),bitemporal=dict(observed=span(1,4),effective=span(1,8)))
            b=dict(write_req('beta','beta',readers=('alice',)),bitemporal=dict(observed=span(4,6),effective=span(3,5)))
            self.assertEqual(s.execute(a,ctx(),10)['outcome'],'ok')
            self.assertEqual(s.execute(b,ctx(),11)['outcome'],'ok')
            def run(axis, who='alice', **kw):
                args=dict(a='node-1',b='node-2',axis=axis,condition_query=cspace(),context=ctx(who),now=20)
                return file_time_relation(ShadowMarkdownStore(tmp,synthetic=True),**dict(args,**kw))
            self.assertEqual(run('observed')['relation'],'before')
            result=run('effective'); self.assertEqual(result['relation'],'contains')
            self.assertEqual(set(result),{'a','b','axis','relation'})
            self.assertEqual(run('effective','bob'),run('effective','bob',b='missing'))
            self.assertEqual(run('observed',condition_query=dict(cspace(),method={'state':'unknown'})),{'error':'CONDITION_DEFERRED'})
            change=dict(b,kind='Write.modify',node_id='node-2',expected_revision=1,caller_token='change',
                        bitemporal=dict(observed=span('unknown',6),effective=span(3,5)))
            self.assertEqual(s.execute(change,ctx(),12)['outcome'],'ok')
            current=run('observed');self.assertEqual((current['relation'], current['b']['revision']),('unknown',2))
