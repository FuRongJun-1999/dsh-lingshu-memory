import inspect
import unittest
from unittest.mock import Mock
from framework import export_locators as mod
from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from test_read_edges import request
from test_shadow_runtime import bitemp, cspace, ctx

SHA='1'*64


def options(**kw):
    public=frozenset({'alice','bob'}); private=frozenset({'alice'})
    nodes={k:Node('t1',1,SHA,1,acl,acl) for k,acl in [('a',public),('b',public),('hidden',private)]}
    meta=dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()))
    return dict(dict(expected=(('b',1,SHA),('a',1,SHA)),generation=4,context=ctx('bob'),now=10,
                     view=ReadSnapshot(4,1,nodes,dict.fromkeys(nodes,meta)),model=Model(),can_export=lambda _:True),**kw)


class ExportLocatorsTests(unittest.TestCase):
    def test_sorted_minimal_manifest(self):
        got=mod.export_locators(request('a'),**options())
        self.assertEqual(got,dict(format='locator_manifest_v1',generation=4,
                                  nodes=[dict(id=k,revision=1,content_sha=SHA) for k in ('a','b')]))

    def test_separate_grant_and_snapshot_binding(self):
        view=Mock(); grant=Mock(return_value=False)
        self.assertEqual(mod.export_locators(request('a'),**options(view=view,can_export=grant)),{'error':'EXPORT_DENIED'})
        self.assertEqual(view.mock_calls,[])
        self.assertEqual(mod.export_locators(request('a'),**options(generation=3)),{'error':'EXPORT_SNAPSHOT_CHANGED'})
        self.assertEqual(mod.export_locators(request('a'),**options(context=ctx('bob',policy_generation=2))),{'error':'POLICY_CHANGED'})

    def test_hidden_missing_or_stale_does_not_return_partial_manifest(self):
        for item in (('hidden',1,SHA),('missing',1,SHA),('b',2,SHA)):
            self.assertEqual(mod.export_locators(request('a'),**options(expected=(('a',1,SHA),item))),{'error':'EXPORT_SCOPE_UNAVAILABLE'})
        text=inspect.getsource(mod);old='if row!=dict(id=key,revision=revision,content_sha=sha):';env={}
        self.assertEqual(text.count(old),1)
        exec(compile(text.replace(old,'if row is None:',1),'<export-version-mutant>','exec'),env)
        self.assertEqual(env['export_locators'](request('a'),**options(expected=(('b',2,SHA),)))['nodes'][0]['revision'],1)
