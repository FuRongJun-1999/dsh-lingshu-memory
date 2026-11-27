import inspect
import unittest
from unittest.mock import Mock, patch
from framework import goal_list as mod
from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from test_read_edges import request
from test_shadow_runtime import bitemp, cspace, ctx

SHA='1'*64


def setup(labels):
    readers=frozenset({'alice','bob'}); private=frozenset({'alice'})
    nodes={k:Node('t1',1,SHA,1,acl,acl) for k,acl in [('a',readers),('b',readers),('hidden',private),('stale',readers)]}
    meta=dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()))
    return dict(candidates=('hidden','stale','b','a','a'),status='active',limit=1,context=ctx('bob'),now=10,
                view=ReadSnapshot(1,1,nodes,dict.fromkeys(nodes,meta)),model=Model(),labels=labels)


class GoalListTests(unittest.TestCase):
    def test_ties_filter_and_limit_with_no_reads_of_hidden_labels(self):
        rows={('a',1,SHA):('active',5),('b',1,SHA):('active',5),('hidden',1,SHA):('active',100),
              ('stale',2,SHA):('active',99)}
        labels=Mock();labels.get.side_effect=rows.get
        data=setup(labels)
        self.assertEqual(mod.list_goals(request('a'),**data),{'goals':[dict(locator=dict(id='a',revision=1,content_sha=SHA),status='active',priority=5)]})
        self.assertNotIn(('hidden',1,SHA),[c.args[0] for c in labels.get.call_args_list])
        self.assertEqual(mod.list_goals(request('a'),**dict(data,status='done')),{'goals':[]})

    def test_empty_requested_scope_still_checks_actor_and_policy(self):
        labels=Mock(); data=setup(labels)
        self.assertEqual(mod.list_goals(request('a'),**dict(data,candidates=(),now=1000)),{'error':'AUTH_REQUIRED'})
        self.assertEqual(mod.list_goals(request('a'),**dict(data,candidates=(),context=ctx(policy_generation=2))),{'error':'POLICY_CHANGED'})
        labels.get.assert_not_called()

    def test_revision_weakening_changes_stale_projection(self):
        stale={('stale',2,SHA):('active',99)};data=setup(stale)
        self.assertEqual(mod.list_goals(request('a'),**data),{'goals':[]})
        src=inspect.getsource(mod);anchor="mark=labels.get((key,locator['revision'],locator['content_sha']))"
        self.assertEqual(src.count(anchor),1); env={}
        exec(compile(src.replace(anchor,"mark=next((v for k,v in labels.items() if k[0]==key),None)",1),'<goal-revision-mutant>','exec'),env)
        with patch.object(mod,'list_goals',env['list_goals']):
            self.assertEqual(mod.list_goals(request('a'),**data)['goals'][0]['locator']['id'],'stale')
