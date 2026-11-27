import inspect
import tempfile
import unittest

from framework import time_anchors as anchors
from framework.contracts import extract_condition_space
from framework.migration import instant
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from shadow_runtime.anchors_port import file_time_anchors
from test_shadow_runtime import ShadowMarkdownStore, cspace, ctx, write_req
from test_time_relation import span


def tick(n):return f'2024-01-{n:02}T00:00:00Z'


class TimeAnchorsTests(unittest.TestCase):
    def test_half_open_and_unknown_with_endpoint_mutant(self):
        start,end=instant(tick(4)),instant(tick(8))
        for bounds,yes in [(span(1,4),False),(span(8,9),False),(span(7,7),False),(span(1,5),True),
             (span(4,8),True),(span('unbounded',5),True),(span(7,'unbounded'),True),(span('unknown',5),False)]:
            self.assertIs(anchors.intersects(bounds,start,end),yes)
        src=inspect.getsource(anchors);guard='start < right[1]';self.assertEqual(src.count(guard),1)
        broken={};exec(compile(src.replace(guard,'start <= right[1]',1),'<anchor-endpoint-mutant>','exec'),broken)
        self.assertTrue(broken['intersects'](span(1,4),start,end))

    def test_hidden_does_not_enter_metadata_or_consume_limit(self):
        everyone=frozenset({'alice','bob'});owner=frozenset({'alice'})
        a=Node('t1',1,'1'*64,1,owner,owner);b=Node('t1',1,'2'*64,1,everyone,everyone)
        meta=dict(condition_space=extract_condition_space(cspace()),bitemporal=dict(observed=span(1,8),effective=span(1,8)))
        args=dict(axis='observed',window_start=tick(4),window_end=tick(6),condition_query=cspace(),limit=1,
                  context=ctx('bob'),now=10, model=Model())
        # 故意没有隐藏节点的元数据；错误读取不会静默成功。
        view=ReadSnapshot(1,1,{'a':a,'b':b},{'b':meta})
        out=anchors.time_anchors(view=view,**args)
        self.assertEqual(out,{'axis':'observed','items':[dict(id='b',revision=1,content_sha='2'*64)]})
        self.assertEqual(out,anchors.time_anchors(view=ReadSnapshot(1,1,{'b':b},{'b':meta}),**args))
        self.assertEqual(anchors.time_anchors(view=view,**dict(args,context=ctx('bob',policy_generation=2))),{'error':'POLICY_CHANGED'})
        for start,end in [(tick(6),tick(4)),(tick(4),tick(4))]:
            with self.assertRaisesRegex(ValueError,'INVALID_WINDOW'):
                anchors.time_anchors(view=view,**dict(args,window_start=start,window_end=end))

    def test_file_uses_current_revision_and_explicit_axis(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=ShadowMarkdownStore(tmp,synthetic=True)
            row=dict(write_req('anchor','fixture visible'),bitemporal=dict(observed=span(1,4),effective=span(2,6)))
            self.assertEqual(store.execute(row,ctx(),10)['outcome'],'ok')
            def observe(axis,**kw):
                args=dict(axis=axis,window_start=tick(4),window_end=tick(8),condition_query=cspace(),limit=2,context=ctx(),now=30)
                return file_time_anchors(ShadowMarkdownStore(tmp,synthetic=True),**dict(args,**kw))
            self.assertEqual(observe('observed')['items'],[])
            self.assertEqual(observe('effective')['items'][0]['revision'],1)
            self.assertEqual(observe('effective',condition_query=dict(cspace(),method={'state':'unknown'}))['items'],[])
            change=dict(row,kind='Write.modify',node_id='node-1',expected_revision=1,caller_token='change',content='fixture revised',
                        bitemporal=dict(observed=span(1,5),effective=span('unknown',6)))
            self.assertEqual(store.execute(change,ctx(),20)['outcome'],'ok')
            self.assertEqual(observe('effective')['items'],[])
            self.assertEqual(observe('observed')['items'][0]['revision'],2)
