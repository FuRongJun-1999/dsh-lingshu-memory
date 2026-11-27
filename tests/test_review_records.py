import inspect
import unittest
from unittest.mock import Mock
from framework import review_records as mod
from framework.spec import digest
from test_shadow_runtime import ctx


def frame():
    return dict(proposal='p',records=[dict(seq=1,decision='edit',revision=1),dict(seq=3,decision='accept',revision=2)])


def args(**kw):
    return dict(dict(proposal='p',expected_sha=digest(frame()),context=ctx(),now=10,allowed=lambda *_:True,
                     snapshot=lambda *_:frame(),limit=1),**kw)


class ReviewRecordsTests(unittest.TestCase):
    def test_bounded_current_snapshot(self):
        source=frame(); got=mod.review_records(**args(snapshot=lambda *_:source))
        self.assertEqual(got,dict(proposal='p',records=[dict(seq=3,decision='accept',revision=2)]))
        got['records'][0]['decision']='reject'
        self.assertEqual(source['records'][-1]['decision'],'accept')

    def test_denied_and_foreign_records_do_not_yield_payload(self):
        port=Mock()
        self.assertEqual(mod.review_records(**args(allowed=lambda *_:False,snapshot=port)),{'error':'NOT_FOUND_OR_DENIED'})
        self.assertEqual(mod.review_records(**args(now=1000,snapshot=port)),{'error':'AUTH_REQUIRED'})
        port.assert_not_called()
        for f in (dict(frame(),proposal='other'),dict(frame(),records=[dict(frame()['records'][0],body='fixture')]),
                  dict(frame(),records=[frame()['records'][0]]*129)):
            self.assertEqual(mod.review_records(**args(snapshot=lambda *_:f)),{'error':'REVIEW_RECORD_INVALID'})

    def test_digest_guard_detects_mutation_outside_output_page(self):
        f=frame();f['records'][0]['decision']='reject';kw=args(snapshot=lambda *_:f)
        self.assertEqual(mod.review_records(**kw),{'error':'REVIEW_RECORD_CHANGED'})
        text=inspect.getsource(mod);guard='if digest(dict(proposal=proposal,records=records))!=expected_sha:'
        self.assertEqual(text.count(guard),1);ns={}
        exec(compile(text.replace(guard,'if False:',1),'<review-digest-mutant>','exec'),ns)
        self.assertEqual(ns['review_records'](**kw)['records'][0]['decision'],'accept')
