import inspect
import unittest
from unittest.mock import Mock
from framework import identity_profile as mod
from framework.spec import digest
from test_shadow_runtime import ctx


def frame():
    return dict(subject='agent:fixture',refs=[dict(kind='anchor',id='a',revision=1,content_sha='1'*64),
                                              dict(kind='trait',id='b',revision=2,content_sha='2'*64)])


def args(**kw):
    return dict(dict(subject='agent:fixture',expected_sha=digest(frame()),context=ctx(),now=10,
                     allowed=lambda *_:True,snapshot=lambda *_:frame()),**kw)


class IdentityProfileTests(unittest.TestCase):
    def test_copies_refs_and_never_returns_content(self):
        f=frame(); result=mod.identity_profile(**args(snapshot=lambda *_:f))
        self.assertEqual(result,f)
        result['refs'][0]['revision']=8
        self.assertEqual(f['refs'][0]['revision'],1)

    def test_denial_and_foreign_subject(self):
        port=Mock()
        self.assertEqual(mod.identity_profile(**args(allowed=lambda *_:False,snapshot=port)),{'error':'NOT_FOUND_OR_DENIED'})
        self.assertEqual(mod.identity_profile(**args(now=1000,snapshot=port)),{'error':'AUTH_REQUIRED'})
        port.assert_not_called()
        self.assertEqual(mod.identity_profile(**args(snapshot=lambda *_:dict(frame(),subject='agent:foreign'))),{'error':'PROFILE_INVALID'})

    def test_revision_binding_and_duplicate_ref(self):
        f=frame();f['refs'][1]['revision']=3;kw=args(snapshot=lambda *_:f)
        self.assertEqual(mod.identity_profile(**kw),{'error':'PROFILE_CHANGED'})
        text=inspect.getsource(mod);guard='if digest(dict(subject=subject,refs=refs))!=expected_sha:'
        self.assertEqual(text.count(guard),1);env={}
        exec(compile(text.replace(guard,'if False:',1),'<profile-digest-mutant>','exec'),env)
        self.assertEqual(env['identity_profile'](**kw)['refs'][1]['revision'],3)
        f['refs'].append(f['refs'][0]);self.assertEqual(mod.identity_profile(**kw),{'error':'PROFILE_INVALID'})
