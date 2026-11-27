import pathlib
import tempfile
import unittest
from framework.verification import issue_proof, proof_applies
from test_shadow_runtime import ShadowMarkdownStore, ctx, write_req


class VerificationCapabilityTests(unittest.TestCase):
    def test_independent_proof_keeps_all_binding_constraints(self):
        subject = dict(node_id='node-1', revision=2, content_sha='1'*64, source_id='fixture-author')
        proof = issue_proof(**subject, verifier_id='fixture-reviewer', scope='restore', method_allowed=True,
                            credential_exists=True, credential_time=5, verified_at=9)
        self.assertTrue(proof_applies(proof, **subject))
        for field, value in [('node_id','node-2'),('revision',3),('content_sha','2'*64),('source_id','other')]:
            self.assertFalse(proof_applies(proof, **dict(subject, **{field:value})))
        self.assertFalse(proof_applies(proof, **subject, required_scope='full'))
        self.assertFalse(proof_applies(dict(proof, verified_at=11), **subject))
        self.assertIsNone(issue_proof(**subject, verifier_id='fixture-author', scope='restore', method_allowed=True,
                                      credential_exists=True, credential_time=5, verified_at=9))

    def test_tampered_proof_cannot_restore_after_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ShadowMarkdownStore(tmp, synthetic=True)
            self.assertEqual(store.execute(write_req('one','blue fixture'),ctx(),10)['outcome'],'ok')
            gov = dict(node_id='node-1', expected_revision=1, reason='fixture')
            self.assertEqual(store.execute(dict(gov,kind='Govern.forget',caller_token='forget'),ctx(),11)['outcome'],'ok')
            restore = dict(gov,kind='Govern.restore',caller_token='restore')
            self.assertEqual(store.execute(restore,ctx(),12)['error_code'],'VERIFICATION_REQUIRED')
            opts = dict(node_id='node-1',expected_revision=1,verifier_id='fixture-reviewer',scope='restore',
                        method_allowed=True,credential_exists=True,credential_time=5,verified_at=12)
            self.assertTrue(store.verify_record(**opts))
            proof_file, = (pathlib.Path(tmp)/'verifications').glob('*.json')
            raw = proof_file.read_bytes()
            self.assertIn(b'"verified_at": 12',raw)
            proof_file.write_bytes(raw.replace(b'"verified_at": 12',b'"verified_at": 13'))
            reopened = ShadowMarkdownStore(tmp, synthetic=True)
            self.assertEqual(reopened.execute(restore,ctx(),14)['error_code'],'VERIFICATION_REQUIRED')
            proof_file.write_bytes(raw)
            self.assertEqual(reopened.execute(restore,ctx(),15)['target']['projection'],'active')

    def test_digest_mutant_cannot_pass_the_original_observation(self):
        from framework import verification
        import inspect
        text = inspect.getsource(verification)
        a = "    if digest(body) != proof['proof_sha']:"
        self.assertEqual(text.count(a),1)
        altered={}
        exec(compile(text.replace(a,'    if False:',1),'<proof-test-mutant>','exec'),altered)
        subject=dict(node_id='x',revision=1,content_sha='1'*64,source_id='fixture-source')
        valid=issue_proof(**subject,verifier_id='fixture-reviewer',scope='full',method_allowed=True,
                          credential_exists=True,credential_time=1,verified_at=5)
        changed=dict(valid,verified_at=7)
        self.assertTrue(proof_applies(valid,**subject))
        self.assertFalse(proof_applies(changed,**subject))
        self.assertTrue(altered['proof_applies'](changed,**subject))
