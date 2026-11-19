import pathlib
import tempfile
import unittest
from test_shadow_runtime import ShadowMarkdownStore, ctx, write_req


class AuditFailureReceiptTests(unittest.TestCase):
    def test_failed_append_survives_reopen_and_unrelated_healthy_audit(self):
        def fail_append(stage, path):
            if stage == 'audit:before_append':
                raise OSError('synthetic audit failure')
        for operation in ('Write.create', 'Govern.forget'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as tmp:
                store = ShadowMarkdownStore(tmp, synthetic=True)
                seed = store.execute(write_req('seed', 'seed'), ctx(), 10)
                self.assertEqual(seed['outcome'], 'ok')
                req = write_req('under-test', 'blue') if operation=='Write.create' else dict(kind=operation,caller_token='under-test',node_id='node-1',expected_revision=1,reason='fixture')
                audit = pathlib.Path(tmp)/'audit/audit.jsonl'
                before = audit.read_bytes()
                initial = store.execute(req, ctx(), 11, fault_hook=fail_append)
                reopened = ShadowMarkdownStore(tmp, synthetic=True)
                responses = [initial, reopened.execute(req, ctx(), 12), reopened.execute(dict(kind='Read.receipt',operation=operation,caller_token='under-test'), ctx(), 13)]
                for out in responses:
                    self.assertEqual((out['error_code'],out['target']['commit_status'],out['target']['audit']),('AUDIT_FAILED','committed','failed'))
                    self.assertEqual(out['historical_receipt']['audit_state'],'failed')
                    self.assertEqual(out['historical_receipt'],initial['historical_receipt'])
                recovered = reopened.recover_token_state(tenant='t1',principal='alice',operation=operation,caller_token='under-test')
                self.assertEqual((recovered['commit_status'],recovered['audit_state']),('committed','failed'))
                self.assertEqual(audit.read_bytes(),before)
