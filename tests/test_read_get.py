import hashlib
import unittest
from dataclasses import replace
from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Model, Node
from framework.read_get import ReadSnapshot, read_get
from test_shadow_runtime import ctx, cspace, bitemp, Q


class ReadGetTests(unittest.TestCase):
    def setUp(self):
        self.text = 'independent blue tile'
        self.sha = hashlib.sha256(self.text.encode()).hexdigest()
        self.node = Node('t1', 1, self.sha, 1, frozenset({'alice'}), frozenset({'alice'}))
        self.meta = dict(condition_space=extract_condition_space(cspace()), bitemporal=time_bundle(bitemp()))
        self.view = ReadSnapshot(2, 1, {'node-1':self.node}, {'node-1':self.meta})
        self.take = dict(kind='Read.get',node_id='node-1',include_provenance=False,
                         condition_query=cspace(),time_axis='effective',time_point=Q)
        self.reads=[]
        self.model=Model()

    def call(self, *, actor=None, live=None, get_body=None, live_actor=None, req=None, live_time=11):
        snapshots=iter([self.view, live or self.view]); actor=actor or ctx()
        def body(key,revision):
            self.reads.append((key,revision));return self.text if get_body is None else get_body
        return read_get(req or self.take, context=actor, now=10, request_id='fixture', snapshot=lambda:next(snapshots),
                        body=body, model=self.model, current_context=lambda:live_actor or actor, current_now=lambda:live_time)

    def test_standalone_current_read_and_no_backend_miss(self):
        no=self.call(actor=ctx('bob')); absent=self.call(req=dict(self.take,node_id='missing'))
        self.assertEqual(no,absent);self.assertEqual(no['error_code'],'NOT_FOUND_OR_DENIED');self.assertEqual(self.reads,[])
        ok=self.call(); self.assertEqual(ok['records'][0]['locator'],dict(id='node-1',revision=1,content_sha=self.sha))
        self.assertEqual(ok['records'][0]['body'],self.text); self.assertEqual(ok['records'][0]['content_type'],'untrusted_markdown')

    def test_no_body_when_temporal_mismatch_or_condition_unknown(self):
        self.assertEqual(self.call(req=dict(self.take,time_point='2024-01-10T00:00:00Z'))['records'],[])
        unknown=dict(cspace(),method={'state':'unknown'})
        self.assertEqual(self.call(req=dict(self.take,condition_query=unknown))['error_code'],'CONDITION_DEFERRED')
        self.assertEqual(self.reads,[])

    def test_no_records_after_revocation_or_integrity_error(self):
        for v in (replace(self.view,nodes={'node-1':replace(self.node,current_readers=frozenset())}),
                  replace(self.view,nodes={'node-1':replace(self.node,revision=2)})):
            out=self.call(live=v);self.assertEqual(out['error_code'],'POLICY_CHANGED');self.assertIsNone(out['records'])
        for kw,code in [({'live_actor':ctx(policy_generation=2)},'POLICY_CHANGED'),({'get_body':'not the committed bytes'},'INTEGRITY_FAILURE')]:
            out=self.call(**kw);self.assertEqual(out['error_code'],code);self.assertIsNone(out['records'])

    def test_expiry_and_same_generation_metadata_mismatch(self):
        self.assertEqual(self.call(live_time=1000)['error_code'], 'POLICY_CHANGED')
        other = dict(self.meta, condition_space=extract_condition_space(dict(cspace(), method={'state':'unknown'})))
        out = self.call(live=replace(self.view, metadata={'node-1':other}))
        self.assertEqual(out['error_code'], 'POLICY_CHANGED');self.assertIsNone(out['records'])

    def test_guard_mutations_change_target_observations(self):
        from unittest.mock import patch
        source = read_get.__code__.co_filename
        with open(source, encoding='utf-8') as f:
            data = f.read()
        check = "    if not allowed(first, key, ctx):"
        compare = " and (node.revision, node.content_sha) == (locator['revision'], locator['content_sha'])"
        for old, new, control, mutant in (
            (check, '    if key not in first.nodes:', {'actor':ctx('bob')}, 'POLICY_CHANGED'),
            (compare, '', {'live':replace(self.view,nodes={'node-1':replace(self.node,revision=2)})}, None),
        ):
            with self.subTest(old=old):
                original = self.call(**control)
                self.assertIsNotNone(original['error_code'])
                before = len(self.reads)
                self.assertEqual(data.count(old),1)
                scope = {}
                exec(compile(data.replace(old,new),source,'exec'),scope)
                with patch.dict(globals(), read_get=scope['read_get']):
                    observed = self.call(**control)
                self.assertEqual(observed['error_code'],mutant)
                self.assertEqual(len(self.reads)-before,1)
