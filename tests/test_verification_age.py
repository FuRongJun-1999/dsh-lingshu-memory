import inspect
import unittest
from unittest.mock import Mock, patch
from framework import verification_age as mod
from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from test_read_edges import request
from test_shadow_runtime import bitemp, cspace, ctx

KEY=('n',1,'1'*64)


def options(**kw):
    acl=frozenset({'alice'});node=Node('t1',1,KEY[2],1,acl,acl)
    meta=dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()),source_attribution={'source_id':'src'})
    return dict(dict(context=ctx(expires_at=200000),now=86410,view=ReadSnapshot(1,1,{'n':node},{'n':meta}),model=Model(),
                     proof=lambda *_:None,metadata=lambda k:dict(key=k,layer='knowledge',created_at=10),min_days=1),**kw)


class VerificationAgeTests(unittest.TestCase):
    def test_inclusive_threshold_without_claim_of_corruption(self):
        call=lambda **kw:mod.inspect_verification_age(request('n'),**options(**kw))['findings']
        self.assertEqual(call(now=86409),[])
        self.assertEqual(call(),['CURRENT_PROOF_NOT_ESTABLISHED'])
        self.assertEqual(call(metadata=lambda k:dict(key=k,layer='contextual',created_at=10)),[])
        with patch.object(mod,'read_status',return_value=dict(status='verified',locator=dict(id='n',revision=1,content_sha=KEY[2]))):
            self.assertEqual(call(),[])

    def test_not_authorized_never_reads_metadata_or_proof(self):
        meta=Mock();proof=Mock()
        got=mod.inspect_verification_age(request('n'),**options(context=ctx('bob',expires_at=200000),metadata=meta,proof=proof))
        self.assertEqual(got,{'error':'NOT_FOUND_OR_DENIED'})
        meta.assert_not_called();proof.assert_not_called()

    def test_invalid_metadata_distinct_and_stale_mutation_detected(self):
        old=dict(key=('n',2,KEY[2]),layer='knowledge',created_at=10)
        for row in (None,old,dict(old,key=KEY,created_at=99999)):
            self.assertEqual(mod.inspect_verification_age(request('n'),**options(metadata=lambda _:row)),{'error':'SCRUB_METADATA_UNKNOWN'})
        text=inspect.getsource(mod);g=" or row['key']!=key";self.assertEqual(text.count(g),1);ns={}
        exec(compile(text.replace(g,'',1),'<scrub-revision-mutant>','exec'),ns)
        self.assertEqual(ns['inspect_verification_age'](request('n'),**options(metadata=lambda _:old))['findings'],['CURRENT_PROOF_NOT_ESTABLISHED'])
