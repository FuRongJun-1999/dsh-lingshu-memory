import inspect
import unittest
from unittest.mock import Mock
from framework import ccg_review_preview as mod
from framework.spec import digest
from test_shadow_runtime import ctx


def candidate():
    return dict(node_id='cand',compiler='actor-a',policy_generation=1,fields=dict.fromkeys(mod.FIELDS,'合成证据'))


def receipt(**kw):
    return dict(dict(node_id='cand',candidate_sha=digest(candidate()),reviewer='actor-b',policy_generation=1,verdict='ACCEPT'),**kw)


def options(**kw):
    return dict(dict(node_id='cand',expected_sha=digest(candidate()),context=ctx(),now=10,
                     allowed=lambda *_:True,snapshot=lambda *_:candidate(),check_receipt=lambda *_:receipt()),**kw)


class CcgPreviewTests(unittest.TestCase):
    def test_only_matching_acceptance_and_no_write(self):
        self.assertEqual(mod.review_preview(**options()),dict(status='review_matches',candidate_sha=digest(candidate()),applied=False))
        for evidence,error in ((None,'CCG_RECEIPT_UNVERIFIED'),(receipt(candidate_sha='0'*64),'CCG_RECEIPT_UNVERIFIED'),
                               (receipt(policy_generation=2),'CCG_RECEIPT_UNVERIFIED'),(receipt(verdict='DEFER'),'CCG_NOT_ACCEPTED')):
            self.assertEqual(mod.review_preview(**options(check_receipt=lambda *_:evidence)),{'error':error})

    def test_denial_and_bad_candidate_do_not_read_receipt(self):
        read=Mock(); check=Mock(); c=candidate()
        self.assertEqual(mod.review_preview(**options(allowed=lambda *_:False,snapshot=read,check_receipt=check)),{'error':'CCG_DENIED'})
        read.assert_not_called()
        c['fields']['执行']='改版'
        self.assertEqual(mod.review_preview(**options(snapshot=lambda *_:c,check_receipt=check)),{'error':'CCG_CANDIDATE_CHANGED'})
        del c['fields']['验证方式']
        self.assertEqual(mod.review_preview(**options(snapshot=lambda *_:c,expected_sha=digest(c),check_receipt=check)),{'error':'CCG_FIELDS_INVALID'})
        check.assert_not_called()

    def test_self_review_and_guard_mutant(self):
        kw=options(check_receipt=lambda *_:receipt(reviewer='actor-a'))
        self.assertEqual(mod.review_preview(**kw),{'error':'CCG_SELF_REVIEW'})
        code=inspect.getsource(mod);guard="if review['reviewer']==candidate['compiler']:";ns={}
        self.assertEqual(code.count(guard),1)
        exec(compile(code.replace(guard,'if False:',1),'<ccg-self-review-mutant>','exec'),ns)
        self.assertEqual(ns['review_preview'](**kw)['status'],'review_matches')
