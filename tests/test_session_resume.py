import inspect
import unittest
from unittest.mock import Mock
from framework import session_resume as mod
from test_shadow_runtime import ctx


def args(**changes):
    return dict(dict(session='s',roles=frozenset({'user'}),recent_limit=2,expected_generation=7,byte_budget=256,
                     context=ctx(),now=10,allowed=lambda *_:True,snapshot=lambda *_:fixture()),**changes)


def fixture():
    return dict(generation=7,events=(dict(session='s',seq=1,role='user',text='甲'),),
                notes=(dict(session='s',id='n1',revision=1,content_sha='a'*64),))


class SessionResumeTests(unittest.TestCase):
    def test_single_snapshot_combines_refs_and_recent_events(self):
        read=Mock(return_value=fixture());got=mod.resume_session(**args(snapshot=read))
        read.assert_called_once()
        self.assertEqual(got,dict(generation=7,events=[dict(seq=1,role='user',text='甲',trust='untrusted_event')],
                                  notes=[dict(id='n1',revision=1,content_sha='a'*64)]))
        self.assertEqual(mod.resume_session(**args(byte_budget=70)),got)
        self.assertEqual(mod.resume_session(**args(byte_budget=69)),{'error':'SESSION_BUDGET'})

    def test_denied_zero_and_stale_never_return_payload(self):
        read=Mock(return_value=fixture())
        self.assertEqual(mod.resume_session(**args(snapshot=read,allowed=lambda *_:False)),{'error':'NOT_FOUND_OR_DENIED'})
        self.assertEqual(mod.resume_session(**args(snapshot=read,byte_budget=0)),{'error':'SESSION_BUDGET'})
        read.assert_not_called()
        self.assertEqual(mod.resume_session(**args(snapshot=read,expected_generation=6)),{'error':'WINDOW_CHANGED'})

    def test_foreign_note_discards_valid_event_and_mutation_is_detected(self):
        frame=fixture();frame['notes'][0]['session']='other';kw=args(snapshot=lambda *_:frame)
        self.assertEqual(mod.resume_session(**kw),{'error':'SESSION_NOTES_INVALID'})
        source=inspect.getsource(mod);guard=" or note['session']!=session"
        self.assertEqual(source.count(guard),1)
        mutant={};exec(compile(source.replace(guard,'',1),'<session-scope-mutant>','exec'),mutant)
        self.assertEqual(mutant['resume_session'](**kw)['notes'][0]['id'],'n1')
