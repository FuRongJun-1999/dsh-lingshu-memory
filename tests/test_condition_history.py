import inspect
import unittest
from unittest.mock import Mock
from framework import condition_history as mod
from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from test_read_edges import request
from test_shadow_runtime import bitemp, cspace, ctx

KEY=('n',3,'1'*64)


def args(history,who='alice'):
    acl=frozenset({'alice'}); node=Node('t1',3,KEY[2],1,acl,acl)
    meta=dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()))
    return dict(context=ctx(who),now=10,view=ReadSnapshot(1,1,{'n':node},{'n':meta}),model=Model(),history=history,limit=1)


def row(revision):return dict(revision=revision,rule='fixture rule',missing='fixture condition')


class ConditionHistoryTests(unittest.TestCase):
    def test_current_binding_and_latest_limit(self):
        p=Mock(return_value=dict(key=KEY,changes=(row(1),row(3))))
        result=mod.condition_history(request('n'),**args(p))
        self.assertEqual(result['changes'],[dict(row(3),trust='untrusted_history')]);p.assert_called_once_with(KEY)

    def test_denial_precedes_history_read(self):
        p=Mock()
        self.assertEqual(mod.condition_history(request('n'),**args(p,'bob')),{'error':'NOT_FOUND_OR_DENIED'})
        p.assert_not_called()

    def test_stale_or_invalid_history_is_not_partial(self):
        for changes in ((row(1),),(row(3),row(3)),(row(4),), (row(3),dict(row(3),missing=' '))):
            self.assertEqual(mod.condition_history(request('n'),**args(lambda _:dict(key=KEY,changes=changes))),{'error':'HISTORY_UNKNOWN'})
        p=lambda _:dict(key=('n',3,'2'*64),changes=(row(3),))
        self.assertEqual(mod.condition_history(request('n'),**args(p)),{'error':'HISTORY_UNKNOWN'})
        text=inspect.getsource(mod);guard=" or frame['key']!=key"
        self.assertEqual(text.count(guard),1);ns={}
        exec(compile(text.replace(guard,'',1),'<history-binding-mutant>','exec'),ns)
        self.assertEqual(ns['condition_history'](request('n'),**args(p))['changes'][0]['revision'],3)
