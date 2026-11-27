import hashlib
import inspect
import tempfile
import unittest
from unittest.mock import Mock

from framework import route_candidates as route
from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from shadow_runtime.route_port import file_route
from test_shadow_runtime import ShadowMarkdownStore, Q, bitemp, cspace, ctx, write_req


def selector(**kw):
    return dict(dict(kind='Read.search',query='fixture',limit=4,include_provenance=False,condition_query=cspace(),
                     time_axis='effective',time_point=Q),**kw)


class RouteTests(unittest.TestCase):
    def test_hidden_candidate_and_unknown_capability_do_not_contribute(self):
        owner=frozenset({'alice'});public=frozenset({'alice','bob'});sha=hashlib.sha256(b'fixture').hexdigest()
        rows={key:Node('t1',1,sha,1,readers,readers) for key,readers in [('a',public),('b',owner),('c',public)]}
        meta={key:dict(condition_space=dict(extract_condition_space(cspace()),attributes={'route.capability':hint}),
                       bitemporal=time_bundle(bitemp())) for key,hint in [('a','visible.tool'),('b','hidden.tool'),('c','not-listed')]}
        body=Mock(return_value='fixture')
        args=dict(context=ctx('bob'),now=10,view=ReadSnapshot(1,1,rows,meta),postings={'fixture':list(rows)},body=body,
                  model=Model(),capabilities=frozenset({'visible.tool','hidden.tool'}))
        result=route.suggest_route(selector(),**args)
        self.assertEqual(result['suggested_capabilities'],['visible.tool'])
        self.assertEqual([x['id'] for x in result['candidates']],['a','c'])
        self.assertEqual([c.args[0] for c in body.call_args_list],['a','c'])
        source=inspect.getsource(route);anchor='if name in capabilities:'
        self.assertEqual(source.count(anchor),1)
        mutant={};exec(compile(source.replace(anchor,'if name is not None:',1),'<route-catalog-mutant>','exec'),mutant)
        self.assertEqual(mutant['suggest_route'](selector(),**args)['suggested_capabilities'],['not-listed','visible.tool'])

    def test_file_projection_tracks_revisions_not_prior_suggestions(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=ShadowMarkdownStore(tmp,synthetic=True)
            def payload(hint):return dict(cspace(),attributes=[dict(key='route.capability',value=hint)])
            a=dict(write_req('alpha','fixture alpha',readers=('alice','bob')),condition_space=payload('visible.tool'))
            b=dict(write_req('beta','fixture beta',readers=('alice',)),condition_space=payload('hidden.tool'))
            for req in (a,b):self.assertEqual(s.execute(req,ctx(),10)['outcome'],'ok')
            def call(who='bob',**kw):
                return file_route(ShadowMarkdownStore(tmp,synthetic=True),selector(**kw),context=ctx(who),now=20,
                                  capabilities=frozenset({'visible.tool','hidden.tool','updated.tool'}))
            original=call();self.assertEqual(original['suggested_capabilities'],['visible.tool']);self.assertEqual(set(original),{'candidates','suggested_capabilities'})
            self.assertEqual(call('guest'),{'candidates':[],'suggested_capabilities':[]})
            changed=dict(a,kind='Write.modify',node_id='node-1',expected_revision=1,caller_token='changed',
                         condition_space=payload('updated.tool'))
            self.assertEqual(s.execute(changed,ctx(),14)['outcome'],'ok')
            new=call(); self.assertEqual(new['suggested_capabilities'],['updated.tool']);self.assertEqual(new['candidates'][0]['revision'],2)

    def test_unconfirmed_selection_returns_no_partial_suggestions(self):
        known=frozenset({'alice'});sha=hashlib.sha256(b'fixture').hexdigest()
        meta=dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()))
        view=ReadSnapshot(1,1,{'a':Node('t1',1,sha,1,known,known)},{'a':meta})
        read=Mock(return_value='fixture');args=dict(context=ctx(),now=10,view=view,postings={'fixture':['a']},body=read,
                                                  model=Model(),capabilities=frozenset({'visible.tool'}))
        self.assertEqual(route.suggest_route(selector(condition_query=dict(cspace(),method={'state':'unknown'})),**args),
                         {'error':'CONDITION_DEFERRED'})
        self.assertEqual(route.suggest_route(selector(),**dict(args,context=ctx(policy_generation=2))),{'error':'POLICY_CHANGED'})
        read.assert_not_called()
