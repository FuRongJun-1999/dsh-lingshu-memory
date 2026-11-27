import inspect
import unittest
from unittest.mock import Mock
from framework import theory_declaration as mod
from framework.spec import digest
from test_shadow_runtime import ctx

ROW=dict(format=1,version='v2',policy_generation=1)


def options(**kw):
    return dict(dict(expected_sha=digest(ROW),accepted=frozenset({'v2'}),context=ctx(),now=10,
                     allowed=lambda _:True,snapshot=lambda _:dict(ROW)),**kw)


class TheoryDeclarationTests(unittest.TestCase):
    def test_explicit_acceptance_and_no_default(self):
        self.assertEqual(mod.check_declaration(**options()),dict(status='declaration_matches',version='v2'))
        self.assertEqual(mod.check_declaration(**options(accepted=frozenset({'v1'}))),{'status':'version_not_accepted'})
        self.assertEqual(mod.check_declaration(**options(snapshot=lambda _:None)),{'status':'undeclared'})

    def test_authorization_before_snapshot_and_policy_drift(self):
        reader=Mock()
        self.assertEqual(mod.check_declaration(**options(allowed=lambda _:False,snapshot=reader)),{'error':'THEORY_DENIED'})
        self.assertEqual(mod.check_declaration(**options(now=1000,snapshot=reader)),{'error':'AUTH_REQUIRED'})
        reader.assert_not_called()
        self.assertEqual(mod.check_declaration(**options(snapshot=lambda _:dict(ROW,policy_generation=2))),{'error':'POLICY_CHANGED'})
        self.assertEqual(mod.check_declaration(**options(snapshot=lambda _:dict(ROW,accepted=['v2']))),{'error':'THEORY_SCHEMA_INVALID'})

    def test_second_accepted_version_still_requires_fixed_digest(self):
        kw=options(accepted=frozenset({'v2','v3'}),snapshot=lambda _:dict(ROW,version='v3'))
        self.assertEqual(mod.check_declaration(**kw),{'error':'THEORY_DECLARATION_CHANGED'})
        source=inspect.getsource(mod); needle='if digest(frame)!=expected_sha:'
        self.assertEqual(source.count(needle),1); ns={}
        exec(compile(source.replace(needle,'if False:',1),'<theory-digest-mutant>','exec'),ns)
        self.assertEqual(ns['check_declaration'](**kw)['version'],'v3')
