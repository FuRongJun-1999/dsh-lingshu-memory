"""Independent expectations for the stage evidence manifest gate (stage-0.1)."""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from framework.spec import ROOT
import scripts.stage_gate as gate_mod


def build(root, **overrides):
    log = root / 'logs/spec.txt'
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('ok\n', encoding='utf-8')
    manifest = {
        'schema': 'stage-manifest/1',
        'stage_id': 'stage-0.1',
        'candidate_sha': 'a' * 40,
        'base_sha': 'b' * 40,
        'scope': 'isolated',
        'claims': [{'id': 'spec-tools', 'statement': 'specification tools pass', 'level': 'I2', 'scope': 'isolated', 'gate_ids': ['spec']}],
        'required_gates': [{'id': 'spec', 'command': 'python scripts/check_all.py', 'exit_code': 0, 'raw_log': 'logs/spec.txt', 'raw_log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(), 'independence': 'I2', 'status': 'PASS'}],
        'not_claimed': ['production', 'm6-migration'],
        'reviewed_by': {'role': 'verifier', 'implementer': False, 'independent': True},
    }
    for key, value in overrides.items():
        if value is None:
            manifest.pop(key, None)
        else:
            manifest[key] = value
    return manifest


def codes(manifest, root):
    return [code for code, _detail in gate_mod.validate(manifest, root)]


class StageGateTests(unittest.TestCase):
    def test_valid_isolated_manifest_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertEqual(codes(build(root), root), [])

    def test_gate_not_run_blocks_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = build(root)
            manifest['required_gates'][0]['status'] = 'NOT_RUN'
            self.assertIn('gate_not_run', codes(manifest, root))

    def test_gate_unknown_blocks_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = build(root)
            manifest['required_gates'][0]['status'] = 'unknown'
            self.assertIn('gate_not_run', codes(manifest, root))

    def test_nonzero_exit_blocks_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = build(root)
            manifest['required_gates'][0]['exit_code'] = 1
            self.assertIn('gate_exit', codes(manifest, root))

    def test_missing_raw_log_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = build(root)
            (root / 'logs/spec.txt').unlink()
            self.assertIn('gate_raw_missing', codes(manifest, root))

    def test_raw_log_sha_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = build(root)
            (root / 'logs/spec.txt').write_text('tampered\n', encoding='utf-8')
            self.assertIn('gate_raw_sha', codes(manifest, root))

    def test_claim_cannot_exceed_its_gate_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = build(root)
            manifest['claims'][0]['level'] = 'I3'
            self.assertIn('claim_level_exceeds_gate', codes(manifest, root))

    def test_claim_referencing_unknown_gate_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = build(root)
            manifest['claims'][0]['gate_ids'] = ['absent']
            self.assertIn('claim_unknown_gate', codes(manifest, root))

    def test_isolated_scope_rejects_production_claim_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = build(root)
            manifest['claims'][0]['scope'] = 'production'
            self.assertIn('claim_scope_escalation', codes(manifest, root))

    def test_isolated_scope_rejects_production_wording(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = build(root)
            manifest['claims'][0]['statement'] = 'production ready for release'
            self.assertIn('claim_production_wording', codes(manifest, root))

    def test_self_signed_review_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = build(root)
            manifest['reviewed_by']['implementer'] = True
            self.assertIn('review_self_signed', codes(manifest, root))

    def test_non_independent_review_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = build(root)
            manifest['reviewed_by']['independent'] = False
            self.assertIn('review_not_independent', codes(manifest, root))

    def test_isolated_scope_must_disclaim_production(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = build(root)
            manifest['not_claimed'] = ['performance']
            self.assertIn('not_claimed_missing', codes(manifest, root))

    def test_duplicate_gate_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = build(root)
            manifest['required_gates'].append(dict(manifest['required_gates'][0]))
            self.assertIn('gate_duplicate', codes(manifest, root))

    def test_candidate_equals_base_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = build(root)
            manifest['candidate_sha'] = manifest['base_sha']
            self.assertIn('commit_id', codes(manifest, root))

    def test_status_file_cannot_be_used_as_gate_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = build(root)
            manifest['required_gates'][0]['raw_log'] = 'spec/acceptance.status.json'
            self.assertIn('gate_readonly_status', codes(manifest, root))

    def test_cli_exit_codes_follow_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = build(root)
            path = root / 'manifest.json'
            path.write_text(json.dumps(manifest), encoding='utf-8')
            good = subprocess.run([sys.executable, '-B', 'scripts/stage_gate.py', '--manifest', str(path)], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(good.returncode, 0, good.stdout)
            manifest['required_gates'][0]['status'] = 'NOT_RUN'
            path.write_text(json.dumps(manifest), encoding='utf-8')
            bad = subprocess.run([sys.executable, '-B', 'scripts/stage_gate.py', '--manifest', str(path)], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(bad.returncode, 1)
            self.assertIn('gate_not_run', bad.stdout)


if __name__ == '__main__':
    unittest.main()