import inspect
import unittest
from unittest.mock import Mock

from framework import protection_check as mod
from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from test_read_edges import request
from test_shadow_runtime import bitemp, cspace, ctx


def args(flags, who='alice'):
    readers=frozenset({'alice'});node=Node('t1',1,'1'*64,1,readers,readers)
    meta=dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()))
    return dict(context=ctx(who),now=10,view=ReadSnapshot(1,1,{'n':node},{'n':meta}),model=Model(),flags=flags)


def marks(**changes):
    return dict(locator=dict(id='n',revision=1,content_sha='1'*64),protected=True,immutable=False) | changes


class ProtectionCheckTests(unittest.TestCase):
    def test_explicit_flags_are_independent(self):
        for protected,immutable in ((True,False),(False,True),(False,False),(True,True)):
            expected=marks(protected=protected,immutable=immutable); port=Mock(return_value=expected)
            self.assertEqual(mod.check_protection(request('n'),**args(port)),expected)
            port.assert_called_once_with('n',1)

    def test_hidden_or_expired_does_not_read(self):
        port=Mock()
        self.assertEqual(mod.check_protection(request('n'),**args(port,'bob')),{'error':'NOT_FOUND_OR_DENIED'})
        self.assertEqual(mod.check_protection(request('n'),**dict(args(port),now=1000)),{'error':'AUTH_REQUIRED'})
        port.assert_not_called()

    def test_unknown_or_replaced_proof_never_reports_flags(self):
        changed=marks(locator=dict(id='n',revision=1,content_sha='2'*64))
        for bad in (None,changed,marks(immutable=0),marks(importance=1)):
            self.assertEqual(mod.check_protection(request('n'),**args(lambda *_:bad)),{'error':'PROTECTION_UNKNOWN'})
        code=inspect.getsource(mod);needle=" or item['locator']!=locator"
        self.assertEqual(code.count(needle),1);env={}
        exec(compile(code.replace(needle,'',1),'<protection-binding-mutant>','exec'),env)
        self.assertIs(env['check_protection'](request('n'),**args(lambda *_:changed))['protected'],True)
