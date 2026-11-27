import hashlib
import unittest
from unittest.mock import Mock
from framework.govern import decide_govern
from framework.recovery_plan import decide_recovery


class GovernRecoveryPlanTests(unittest.TestCase):
    def test_govern_denial_and_precondition_fail_before_proof(self):
        meta = dict(tenant='t1', creation_readers=['alice'], declared_sensitivity=2, state='tombstoned', revision=2)
        actor = dict(tenant='t1', principal='alice', clearance=2)
        req = dict(kind='Govern.restore', expected_revision=2)
        proof = Mock(return_value=True)
        for change, code in [(dict(context=dict(actor, tenant='t2')), 'NOT_FOUND_OR_DENIED'),
                             (dict(context=dict(actor, principal='bob')), 'NOT_FOUND_OR_DENIED'),
                             (dict(req=dict(req, expected_revision=1)), 'REVISION_CONFLICT'),
                             (dict(metadata=dict(meta, state='active')), 'STATE_CONFLICT')]:
            kw = dict(req=req, context=actor, metadata=meta)
            kw.update(change)
            with self.assertRaisesRegex(ValueError, code):
                decide_govern(kw.pop('req'), verify_restore=proof, **kw)
        proof.assert_not_called()
        self.assertEqual(decide_govern(req, context=actor, metadata=meta, verify_restore=proof), ('active',))
        proof.assert_called_once_with()
        with self.assertRaisesRegex(ValueError, 'VERIFICATION_REQUIRED'):
            decide_govern(req, context=actor, metadata=meta, verify_restore=lambda: False)

    def test_govern_refuses_widening_and_uses_all_four_actions(self):
        meta = dict(tenant='t1', creation_readers=['alice'], declared_sensitivity=2, state='active', revision=2)
        actor = dict(tenant='t1', principal='alice', clearance=2)
        safe = dict(declared_sensitivity=2, reader_ceiling=['alice'])
        proof = Mock(side_effect=AssertionError('unexpected proof read'))
        for kind, result in [('forget', ('tombstoned',)), ('change_policy', ('active',)),
                             ('correct_revision', ('superseded', 'new_active'))]:
            req = dict(kind='Govern.'+kind, expected_revision=2, replacement=safe, **safe)
            self.assertEqual(decide_govern(req, context=actor, metadata=meta, verify_restore=proof), result)
            if kind != 'forget':
                broad = dict(declared_sensitivity=1, reader_ceiling=['alice','bob'])
                with self.assertRaisesRegex(ValueError, 'POLICY_WIDENING_UNSUPPORTED'):
                    decide_govern(dict(req, replacement=broad, **broad), context=actor, metadata=meta, verify_restore=proof)
        proof.assert_not_called()

    def test_recovery_rejects_unknown_and_ambiguous_evidence(self):
        sha = lambda raw: hashlib.sha256(raw).hexdigest()
        intent = dict(state='prepared', before_manifest_sha=sha(b'{"epoch":1}'), after_manifest_sha=sha(b'{"epoch":2}'))
        self.assertEqual(decide_recovery(intent, {'epoch':1}), 'rollback')
        self.assertEqual(decide_recovery(intent, {'epoch':2}), 'rollforward')
        self.assertEqual(decide_recovery(dict(intent, state='complete'), {}), 'skip')
        with self.assertRaisesRegex(ValueError, 'diverged'):
            decide_recovery(intent, {'epoch':3})
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            decide_recovery(dict(intent, after_manifest_sha=intent['before_manifest_sha']), {'epoch':1})

    def test_recovery_mutant_accepts_conflicting_evidence(self):
        import inspect
        from framework import recovery_plan
        source = inspect.getsource(recovery_plan)
        old = '    if before == after:'
        self.assertEqual(source.count(old), 1)
        both = hashlib.sha256(b'{"epoch":1}').hexdigest()
        intent = dict(state='prepared', before_manifest_sha=both, after_manifest_sha=both)
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            decide_recovery(intent, {'epoch':1})
        mutant = {}
        exec(compile(source.replace(old, '    if not before and not after:', 1), '<test-mutant>', 'exec'), mutant)
        self.assertEqual(mutant['decide_recovery'](intent, {'epoch':1}), 'rollback')
