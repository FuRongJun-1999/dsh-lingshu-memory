import unittest
from types import ModuleType
from pathlib import Path
from framework.write_token import decide_write
from test_shadow_runtime import write_req


class WriteTokenTests(unittest.TestCase):
    def setUp(self):
        self.req = write_req('once', 'synthetic tile')

    def decide(self, fn=decide_write, **changes):
        data = dict(token=None, token_corrupt=False, intent=None, intent_corrupt=False)
        return fn(self.req, **dict(data, **changes))

    def test_first_apply_requires_both_evidence_sources_clear(self):
        initial = self.decide()
        self.assertEqual(initial.action, 'first_apply_candidate')
        self.assertEqual(self.decide(intent={'fingerprint':initial.fingerprint}).action, 'query_only')
        self.assertEqual(self.decide(intent={'fingerprint':'0'*64}).action, 'conflict')
        self.assertEqual(self.decide(intent_corrupt=True).action, 'integrity_failure')
        self.assertEqual(self.decide(token_corrupt=True).action, 'integrity_failure')

    def test_complete_commit_and_cancellation_do_not_reapply(self):
        fp = self.decide().fingerprint
        prior = dict(fingerprint=fp, commit_status='committed', history_complete=True, negative_basis='unassessed')
        self.assertEqual(self.decide(token=prior).action, 'return_original')
        self.assertEqual(self.decide(token=dict(prior,fingerprint='0'*64)).action, 'conflict')
        self.assertEqual(self.decide(token=dict(prior,history_complete=False)).action, 'query_only')
        self.assertEqual(self.decide(token=dict(prior,commit_status='unknown')).action, 'query_only')
        cancelled = dict(prior,commit_status='absent',negative_basis='durable_cancel',fingerprint=None)
        self.assertEqual(self.decide(token=cancelled).action, 'return_original_cancel')

    def test_mutants_change_the_intent_and_replay_decisions(self):
        source = Path(decide_write.__code__.co_filename).read_text(encoding='utf-8')
        fp = self.decide().fingerprint
        token = dict(fingerprint=fp,commit_status='committed',history_complete=True,negative_basis='unassessed')
        checks = [('        if intent is None:', '        if True:', {'intent':{'fingerprint':fp}}, 'query_only'),
                  ('    return WriteDecision(action, fp)', "    return WriteDecision('first_apply_candidate', fp)", {'token':token}, 'return_original')]
        for old, new, evidence, expected in checks:
            self.assertEqual(self.decide(**evidence).action,expected)
            self.assertEqual(source.count(old),1)
            scope = ModuleType('_write_token_mutant')
            exec(compile(source.replace(old,new,1),'<write-token-mutant>','exec'),scope.__dict__)
            self.assertEqual(self.decide(scope.decide_write,**evidence).action,'first_apply_candidate')
