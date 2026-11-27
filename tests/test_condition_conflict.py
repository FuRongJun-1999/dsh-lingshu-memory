import inspect
import unittest
from framework import condition_conflict as mod
from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from test_read_edges import request
from test_shadow_runtime import bitemp, cspace, ctx

SHA='1'*64
KEY=('root',1,SHA)


def args(*rows):
    open_acl=frozenset({'alice','bob'}); closed=frozenset({'alice'})
    nodes={k:Node('t1',1,SHA,1,acl,acl) for k,acl in [('root',open_acl),('visible',open_acl),('hidden',closed)]}
    meta=dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()))
    return dict(positive=frozenset({'office'}),negative=frozenset({'lab'}),context=ctx('bob'),now=10,
                view=ReadSnapshot(1,1,nodes,dict.fromkeys(nodes,meta)),model=Model(),bindings={KEY:rows})


def row(key, rev=1,left=('lab',),right=('office',)):
    return key,rev,SHA,frozenset(left),frozenset(right)


class ConditionConflictTests(unittest.TestCase):
    def test_both_cross_directions_and_no_same_side_clash(self):
        got=mod.check_conditions(request('root'),**args(row('visible')))
        self.assertEqual(got,dict(status='EXACT_CONFLICT',conflicts=[dict(locator=dict(id='visible',revision=1,content_sha=SHA),conditions=['lab','office'])]))
        self.assertEqual(mod.check_conditions(request('root'),**args(row('visible',left=('office',),right=('lab',)))),dict(status='NO_EXACT_CONFLICT',conflicts=[]))

    def test_hidden_and_old_revision_do_not_project(self):
        data=args(row('hidden'),row('visible',2))
        self.assertEqual(mod.check_conditions(request('root'),**data),dict(status='NO_EXACT_CONFLICT',conflicts=[]))
        src=inspect.getsource(mod); guard=" or (candidate['revision'],candidate['content_sha'])!=(revision,sha)"
        self.assertEqual(src.count(guard),1); env={}
        exec(compile(src.replace(guard,'',1),'<condition-revision-mutant>','exec'),env)
        self.assertEqual(env['check_conditions'](request('root'),**data)['conflicts'][0]['locator']['id'],'visible')
        self.assertEqual(mod.check_conditions(request('hidden'),**data),{'error':'NOT_FOUND_OR_DENIED'})

    def test_unavailable_and_malformed_scope_do_not_claim_consistency(self):
        self.assertEqual(mod.check_conditions(request('root'),**dict(args(),bindings={})),{'error':'CONDITION_SCOPE_UNKNOWN'})
        for rows in ((row('visible'),)*129,(row('visible'),row('visible')),(row('visible',left=('office',)),)):
            self.assertEqual(mod.check_conditions(request('root'),**args(*rows)),{'error':'CONDITION_SCOPE_UNKNOWN'})
