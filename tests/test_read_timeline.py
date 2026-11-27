import inspect
import tempfile
import unittest

from framework import read_timeline as timeline
from framework.contracts import extract_condition_space
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from shadow_runtime.timeline_port import file_timeline
from test_shadow_runtime import ShadowMarkdownStore, cspace, ctx, write_req
from test_time_relation import span


class TimelineTests(unittest.TestCase):
    def test_hidden_rows_do_not_consume_limit_and_mutation_leaks(self):
        all_readers=frozenset({'alice','bob'}); owner=frozenset({'alice'})
        def node(readers):return Node('t1',1,'1'*64,1,readers,readers)
        conditions=extract_condition_space(cspace())
        def meta(start):return dict(condition_space=conditions,bitemporal=dict(observed=span(start,9),effective=span(start,9)))
        nodes={'a':node(all_readers),'b':node(all_readers),'hidden':node(owner)}
        metadata={'a':meta(2),'b':meta(2),'hidden':meta(4)}
        args=dict(axis='observed',point='2024-01-05T00:00:00Z',condition_query=cspace(),limit=1,context=ctx('bob'),now=10,model=Model())
        normal=timeline.read_timeline(view=ReadSnapshot(1,1,nodes,metadata),**args)
        absent=timeline.read_timeline(view=ReadSnapshot(1,1,{k:v for k,v in nodes.items() if k!='hidden'},metadata),**args)
        self.assertEqual(normal,absent)
        self.assertEqual(normal,dict(axis='observed',items=[dict(id='a',revision=1,content_sha='1'*64)]))
        src=inspect.getsource(timeline)
        old="if not model.can_read(key, view.nodes, tenant=actor['tenant'], principal=actor['principal'], clearance=actor['clearance']):"
        self.assertEqual(src.count(old),1)
        mutant={}
        exec(compile(src.replace(old,'if False:',1),'<timeline-auth-mutant>','exec'),mutant)
        wrong=mutant['read_timeline'](view=ReadSnapshot(1,1,nodes,metadata),**args)
        self.assertEqual([x['id'] for x in wrong['items']],['hidden'])

    def test_deferred_empty_and_wrong_generation(self):
        readers=frozenset({'alice'});node=Node('t1',1,'1'*64,1,readers,readers)
        args=dict(axis='effective',point='2024-01-05T00:00:00Z',condition_query=cspace(),limit=2,context=ctx(),now=10,model=Model())
        for bound in (span('unknown',9),span('unbounded',9),span(2,5),span(5,5)):
            meta=dict(condition_space=extract_condition_space(cspace()),bitemporal=dict(observed=span(1,9),effective=bound))
            view=ReadSnapshot(1,1,{'a':node},{'a':meta})
            self.assertEqual(timeline.read_timeline(view=view,**args),dict(axis='effective',items=[]))
            self.assertEqual(timeline.read_timeline(view=view,**dict(args,context=ctx(policy_generation=2))),{'error':'POLICY_CHANGED'})
            self.assertEqual(timeline.read_timeline(view=view,**dict(args,now=1000)),{'error':'AUTH_REQUIRED'})
            with self.assertRaisesRegex(ValueError,'AXIS_REQUIRED'):
                timeline.read_timeline(view=view,**dict(args,axis=None))

    def test_file_timeline_current_revisions_and_distinct_axes(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=ShadowMarkdownStore(tmp,synthetic=True)
            a=dict(write_req('a','alpha',readers=('alice','bob')), bitemporal=dict(observed=span(1,9),effective=span(3,9)))
            b=dict(write_req('b','beta',readers=('alice','bob')), bitemporal=dict(observed=span(4,9),effective=span(2,9)))
            for req in (a,b):self.assertEqual(s.execute(req,ctx(),10)['outcome'],'ok')
            def observe(axis):
                return file_timeline(ShadowMarkdownStore(tmp,synthetic=True),axis=axis,point='2024-01-05T00:00:00Z',
                                     condition_query=cspace(),limit=2,context=ctx('bob'),now=30)['items']
            self.assertEqual([x['id'] for x in observe('observed')],['node-2','node-1'])
            self.assertEqual([x['id'] for x in observe('effective')],['node-1','node-2'])
            change=dict(b,kind='Write.modify',node_id='node-2',expected_revision=1,caller_token='changed',content='beta v2',
                        bitemporal=dict(observed=span(2,9),effective=span('unknown',9)))
            self.assertEqual(s.execute(change,ctx(),20)['outcome'],'ok')
            self.assertEqual([(x['id'],x['revision']) for x in observe('observed')],[('node-2',2),('node-1',1)])
            self.assertEqual([x['id'] for x in observe('effective')],['node-1'])
