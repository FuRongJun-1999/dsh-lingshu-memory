import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from framework.read_status import read_status
from shadow_runtime.status_port import file_status
from shadow_runtime.store import ShadowMarkdownStore
from test_shadow_runtime import Q, bitemp, cspace, ctx, write_req


def request(**changes):
    base = dict(kind='Read.get',node_id='node-1',include_provenance=False,condition_query=cspace(),
                time_axis='effective',time_point=Q)
    return dict(base, **changes)


class ReadStatusTests(unittest.TestCase):
    def test_denied_or_inapplicable_never_reads_proof(self):
        digest = '1'*64
        node = Node('t1',1,digest,1,frozenset({'alice'}),frozenset({'alice'}))
        meta = dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()),
                    source_attribution={'source_id':'author-1'})
        view = ReadSnapshot(1,1,{'node-1':node},{'node-1':meta})
        proof = Mock()
        for who, req, expected in [('bob',request(),{'error':'NOT_FOUND_OR_DENIED'}),
                                   ('alice',request(node_id='missing'),{'error':'NOT_FOUND_OR_DENIED'}),
                                   ('alice',request(time_point='2024-01-10T00:00:00Z'),{'status':'not_applicable'}),
                                   ('alice',request(condition_query=dict(cspace(),method={'state':'unknown'})),
                                    {'error':'CONDITION_DEFERRED'})]:
            self.assertEqual(read_status(req,context=ctx(who),now=10,view=view,model=Model(),proof=proof),expected)
        proof.assert_not_called()

    def test_file_status_requires_current_full_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ShadowMarkdownStore(tmp,synthetic=True)
            self.assertEqual(store.execute(write_req('one','blue fixture',readers=('alice',)),ctx(),10)['outcome'],'ok')
            def status(who='alice'):
                return file_status(ShadowMarkdownStore(tmp,synthetic=True),request(),context=ctx(who),now=30)
            def verify(scope):
                return store.verify_record(node_id='node-1',expected_revision=1,verifier_id='fixture-reviewer',
                                           scope=scope,method_allowed=True,credential_exists=True,credential_time=5,verified_at=13)
            self.assertEqual(status()['status'],'unverified')
            self.assertTrue(verify('restore'))
            self.assertEqual(status()['status'],'unverified')
            self.assertTrue(verify('full'))
            good = status(); self.assertEqual(good['status'],'verified'); self.assertEqual(set(good),{'status','locator'})
            self.assertEqual(status('bob'),{'error':'NOT_FOUND_OR_DENIED'})
            p, = (Path(tmp)/'verifications').glob('*.json')
            p.write_bytes(b'{')
            self.assertEqual(status()['status'],'unverified')
            self.assertTrue(verify('full'))
            second = dict(write_req('two','new fixture',readers=('alice',)), kind='Write.modify',node_id='node-1',expected_revision=1)
            self.assertEqual(store.execute(second,ctx(),20)['outcome'],'ok')
            after = status(); self.assertEqual((after['status'],after['locator']['revision']),('unverified',2))

    def test_future_proof_guard_has_observable_counterexample(self):
        import inspect
        from framework import read_status as status_module
        from framework.verification import issue_proof
        body_sha = '1'*64
        node = Node('t1',1,body_sha,1,frozenset({'alice'}),frozenset({'alice'}))
        meta = dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()),
                    source_attribution={'source_id':'author-1'})
        proof = issue_proof(node_id='node-1',revision=1,content_sha=body_sha,source_id='author-1',
                            verifier_id='fixture-reviewer',scope='full',method_allowed=True,
                            credential_exists=True,credential_time=5,verified_at=13)
        inputs = dict(context=ctx(),view=ReadSnapshot(1,1,{'node-1':node},{'node-1':meta}),
                      model=Model(),proof=lambda *_:proof)
        self.assertEqual(read_status(request(),now=13,**inputs)['status'],'verified')
        self.assertEqual(read_status(request(),now=12,**inputs)['status'],'unverified')
        source = inspect.getsource(status_module)
        guard = " and evidence['verified_at'] <= now"
        self.assertEqual(source.count(guard),1)
        isolated = {}
        exec(compile(source.replace(guard,'',1),'<status-guard-mutant>','exec'),isolated)
        self.assertEqual(isolated['read_status'](request(),now=12,**inputs)['status'],'verified')
