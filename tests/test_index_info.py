import inspect
import unittest
from unittest.mock import Mock
from framework import index_info as mod
from test_shadow_runtime import ctx


def frame():
    row=dict(generation=4,node_count=2,sha256='1'*64)
    return dict(policy_generation=1,memory=dict(row),disk=dict(row))


def call(f,**kw):
    opts=dict(expected_generation=4,context=ctx(),now=10,allowed=lambda _:True,snapshot=lambda _:f)
    return mod.index_info(**(opts|kw))


class IndexInfoTests(unittest.TestCase):
    def test_equal_count_is_not_equal_index(self):
        f=frame();self.assertEqual(call(f)['status'],'observations_match')
        f['disk']['sha256']='2'*64
        self.assertEqual(call(f)['status'],'same_generation_mismatch')
        src=inspect.getsource(mod);old="(memory['node_count'],memory['sha256'])!=(disk['node_count'],disk['sha256'])"
        self.assertEqual(src.count(old),1); ns={}
        exec(compile(src.replace(old,"memory['node_count']!=disk['node_count']",1),'<count-only-mutant>','exec'),ns)
        got=ns['index_info'](expected_generation=4,context=ctx(),now=10,allowed=lambda _:True,snapshot=lambda _:f)
        self.assertEqual(got['status'],'observations_match')
        f['disk']['generation']=5
        self.assertEqual(call(f)['status'],'generation_mismatch')

    def test_denial_never_reads_and_policy_rejects(self):
        p=Mock()
        self.assertEqual(call(frame(),allowed=lambda _:False,snapshot=p),{'error':'INFO_DENIED'})
        self.assertEqual(call(frame(),now=1000,snapshot=p),{'error':'AUTH_REQUIRED'})
        p.assert_not_called()
        self.assertEqual(call(dict(frame(),policy_generation=2)),{'error':'POLICY_CHANGED'})

    def test_missing_malformed_and_stale_are_distinct(self):
        self.assertEqual(call(dict(frame(),disk=None)),{'status':'unknown'})
        self.assertEqual(call(dict(frame(),disk={})),{'error':'INDEX_EVIDENCE_INVALID'})
        self.assertEqual(call(frame(),expected_generation=3),{'error':'INDEX_SNAPSHOT_CHANGED'})
