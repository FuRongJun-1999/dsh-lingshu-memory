import inspect
import unittest
from unittest.mock import Mock
from framework import self_state_card as mod
from test_shadow_runtime import ctx


def card():
    return dict(subject='self:fixture',generation=7,policy_generation=1,
                dimensions=dict(task=dict(id='n',revision=1,content_sha='1'*64),person=None,session=None,time=None,trust=None))


def options(**kw):
    return dict(dict(subject='self:fixture',generation=7,context=ctx(),now=10,
                     allowed=lambda *_:True,snapshot=lambda *_:card()),**kw)


class SelfStateCardTests(unittest.TestCase):
    def test_minimal_snapshot_returns_copy(self):
        row=card(); got=mod.read_self_card(**options(snapshot=lambda *_:row))
        self.assertEqual(got,dict(subject=row['subject'],generation=7,dimensions=row['dimensions']))
        got['dimensions']['task']['revision']=9
        self.assertEqual(row['dimensions']['task']['revision'],1)

    def test_rejection_precedes_read(self):
        port=Mock()
        for extra in (dict(now=1000),dict(allowed=lambda *_:False)):
            self.assertIn(mod.read_self_card(**options(snapshot=port,**extra))['error'],('AUTH_REQUIRED','NOT_FOUND_OR_DENIED'))
        port.assert_not_called()

    def test_versions_and_foreign_data_are_rejected(self):
        self.assertEqual(mod.read_self_card(**options(generation=8)),{'error':'SELF_CARD_CHANGED'})
        changed=dict(card(),policy_generation=2); kw=options(snapshot=lambda *_:changed)
        self.assertEqual(mod.read_self_card(**kw),{'error':'SELF_CARD_CHANGED'})
        text=inspect.getsource(mod); needle=" or row['policy_generation']!=actor['policy_generation']"
        self.assertEqual(text.count(needle),1); env={}
        exec(compile(text.replace(needle,'',1),'<self-policy-mutant>','exec'),env)
        self.assertEqual(env['read_self_card'](**kw)['dimensions']['task']['id'],'n')
        changed['subject']='self:foreign'
        self.assertEqual(mod.read_self_card(**kw),{'error':'SELF_CARD_INVALID'})
