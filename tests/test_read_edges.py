import inspect
import tempfile
import unittest

from framework import read_edges as edge_module
from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Edge, Model, Node
from framework.read_get import ReadSnapshot
from shadow_runtime.edges_port import file_edges
from test_shadow_runtime import ShadowMarkdownStore, Q, bitemp, cspace, ctx, write_req


def request(node_id, **changes):
    return dict(dict(kind='Read.get', node_id=node_id, include_provenance=False,
                     condition_query=cspace(), time_axis='effective', time_point=Q), **changes)


class ReadEdgesTests(unittest.TestCase):
    def create(self, store, token, readers, *, edges=()):
        req = write_req(token, token, readers=readers)
        req['source_edges'] = list(edges)
        out = store.execute(req, ctx(), 10)
        self.assertEqual(out['outcome'], 'ok')
        row = out['historical_receipt']
        return dict(id=row['node_id'], revision=row['revision'], content_sha=row['content_sha'])

    def test_hidden_edge_does_not_change_visible_output_and_fault_is_observable(self):
        sha = '1'*64
        actors = frozenset({'alice','bob'})
        def node(readers=actors, edges=()):
            return Node('t1',1,sha,1,readers,readers,edges)
        visible, hidden = Edge('p','corroborating',1,sha), Edge('h','corroborating',1,sha)
        meta = dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()))
        def observe(fn, edges):
            view = ReadSnapshot(1,1,{'root':node(edges=edges),'p':node(),'h':node(frozenset({'alice'}))},
                                {'root':meta,'p':meta,'h':meta})
            return fn(request('root'),context=ctx('bob'),now=10,view=view,model=Model())
        expected = dict(locator=dict(id='root',revision=1,content_sha=sha),
                        edges=[dict(relation='corroborating',target=dict(id='p',revision=1,content_sha=sha))])
        self.assertEqual(observe(edge_module.read_edges,(visible,hidden)),expected)
        self.assertEqual(observe(edge_module.read_edges,(visible,)),expected)
        source = inspect.getsource(edge_module)
        old = "not allowed(edge.target) or edge.relation == 'unknown'"
        self.assertEqual(source.count(old),1)
        isolated = {}
        exec(compile(source.replace(old,"edge.relation == 'unknown'",1),'<edge-projection-mutant>','exec'),isolated)
        self.assertEqual([x['target']['id'] for x in observe(isolated['read_edges'],(visible,hidden))['edges']],['p','h'])

    def test_file_projection_revision_change_refuses_stale_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ShadowMarkdownStore(tmp,synthetic=True)
            target = self.create(store,'target',('alice','bob'))
            edge = dict(node_id=target['id'],relation='derived',revision=1,content_sha=target['content_sha'])
            root = self.create(store,'root',('alice','bob'),edges=[edge])
            def view(req, who='bob'):
                return file_edges(ShadowMarkdownStore(tmp,synthetic=True),req,context=ctx(who),now=30)
            self.assertEqual(view(request(root['id'])),dict(locator=root,edges=[dict(relation='derived',target=target)]))
            self.assertEqual(view(request(root['id']),who='guest'),view(request('absent')))
            self.assertEqual(view(request(root['id'],time_point='2024-01-10T00:00:00Z')),{'status':'not_applicable'})
            edited = dict(write_req('new','target v2'),kind='Write.modify',node_id=target['id'],expected_revision=1)
            self.assertEqual(store.execute(edited,ctx(),20)['outcome'],'ok')
            self.assertEqual(view(request(root['id'])),{'error':'NOT_FOUND_OR_DENIED'})

    def test_target_condition_mismatch_or_unknown_is_omitted(self):
        sha='1'*64
        actors=frozenset({'alice','bob'})
        node=Node('t1',1,sha,1,actors,actors)
        root=Node('t1',1,sha,1,actors,actors,(Edge('p','derived',1,sha),))
        base=dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()))
        for slot in ({'state':'unknown'},{'state':'declared','text':'different'}):
            meta=dict(base,condition_space=extract_condition_space(dict(cspace(),method=slot)))
            view=ReadSnapshot(1,1,{'root':root,'p':node},{'root':base,'p':meta})
            self.assertEqual(edge_module.read_edges(request('root'),context=ctx(),now=10,view=view,model=Model())['edges'],[])
