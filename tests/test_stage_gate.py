"""Independent expectations for the stage manifest gate (schema v3)."""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from framework.spec import ROOT
import scripts.stage_gate as gate_mod


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace')


def commit_all(root, message):
    git(root, 'add', '-A')
    result = subprocess.run(['git', '-c', 'user.email=t@example.invalid', '-c', 'user.name=t',
                             'commit', '-q', '-m', message], cwd=root, capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)


def write_lf(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        handle.write(text)


def evidence(root, gate='spec', command='python scripts/check_all.py', exit_code=0, body='ok'):
    path = root / 'evidence' / (gate + '.log')
    path.parent.mkdir(parents=True, exist_ok=True)
    header = json.dumps({'gate': gate, 'command': command, 'exit_code': exit_code}, sort_keys=True)
    write_lf(path, header + chr(10) + body + chr(10))
    return path


def repo(root, manifest_builder):
    git(root, 'init', '-q')
    evidence(root)
    (root / 'notes.txt').write_text('n1' + chr(10), encoding='utf-8')
    commit_all(root, 'one')
    (root / 'notes.txt').write_text('n2' + chr(10), encoding='utf-8')
    commit_all(root, 'two')
    base = git(root, 'rev-parse', 'HEAD~1').stdout.strip()
    candidate = git(root, 'rev-parse', 'HEAD').stdout.strip()
    manifest = manifest_builder(root, base, candidate)
    (root / 'requirements.json').write_text(json.dumps({'required_gate_ids': ['spec'], 'min_level': 'I2'}), encoding='utf-8')
    manifest['base_sha'] = base
    manifest['candidate_sha'] = candidate
    log_sha = hashlib.sha256((root / 'evidence/spec.log').read_bytes()).hexdigest()
    manifest['gates'][0]['raw_log_sha256'] = log_sha
    rebuilt = {k: v for k, v in manifest.items() if k != 'manifest_sha256'}
    return gate_mod.build_manifest(rebuilt), base, candidate


def body(root=None):
    return {
        'schema': 'stage-manifest/3',
        'stage_id': 'stage-0.1',
        'candidate_sha': 'a' * 40,
        'base_sha': 'b' * 40,
        'scope': 'isolated',
        'required_min_level': 'I2',
        'gates': [{'id': 'spec', 'command': 'python scripts/check_all.py', 'exit_code': 0,
                   'raw_log': 'evidence/spec.log', 'raw_log_sha256': '0' * 64,
                   'independence': 'I2', 'status': 'PASS'}],
        'claims': [{'id': 'spec-tools', 'statement': 'specification tools pass', 'level': 'I2',
                    'scope': 'isolated', 'gate_ids': ['spec']}],
        'not_claimed': ['production', 'm6-migration'],
        'reviewed_by': {'implementer_id': 'impl', 'reviewer_id': 'ver', 'role': 'independent-verifier',
                        'independent': True, 'session': 's', 'window_start': '2026-01-01T00:00:00Z',
                        'window_end': '2026-01-01T01:00:00Z'},
    }


def checks(manifest, root):
    requirements = json.loads((root / 'requirements.json').read_text(encoding='utf-8'))
    return [code for code, _detail in gate_mod.validate(manifest, root, requirements)]


class StageGateV3Tests(unittest.TestCase):
    def test_committed_evidence_with_matching_header_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, _base, _candidate = repo(root, lambda r, b, c: body())
            self.assertEqual(checks(manifest, root), [])

    def test_failed_log_cannot_claim_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, _b, _c = repo(root, lambda r, b, c: body())
            gate_mod.git(root, 'reset', '--soft', 'HEAD~1')
            evidence(root, body='FAILED (3 errors)')
            commit_all(root, 'failed log')
            new_candidate = gate_mod.git(root, 'rev-parse', 'HEAD').stdout.strip()
            manifest['candidate_sha'] = new_candidate
            code = checks(manifest, root)
            self.assertTrue('evidence_mismatch' in code or 'gate_raw_sha' in code, code)

    def test_committed_bytes_replace_declared_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, _b, _c = repo(root, lambda r, b, c: body())
            write_lf(root / 'evidence/spec.log', 'tampered' + chr(10))
            commit_all(root, 'tampered evidence')
            manifest['candidate_sha'] = gate_mod.git(root, 'rev-parse', 'HEAD').stdout.strip()
            self.assertIn('gate_raw_sha', checks(manifest, root))

    def test_evidence_outside_prefix_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            def mutate(r, b, c):
                payload = body()
                payload['gates'][0]['raw_log'] = 'notes.txt'
                return payload
            manifest, _b, _c = repo(root, mutate)
            self.assertIn('gate_raw_path', checks(manifest, root))

    def test_reused_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            def mutate(r, b, c):
                payload = body()
                payload['gates'].append(dict(payload['gates'][0], id='spec2'))
                return payload
            manifest, _b, _c = repo(root, mutate)
            self.assertIn('gate_raw_reused', checks(manifest, root))

    def test_missing_requirements_file_is_a_validator_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, _b, _c = repo(root, lambda r, b, c: body())
            (root / 'requirements.json').unlink()
            path = root / 'manifest.json'
            path.write_text(json.dumps(manifest, sort_keys=True), encoding='utf-8')
            result = subprocess.run([sys.executable, '-B', 'scripts/stage_gate.py', '--manifest', str(path)], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 2)

    def test_requirements_registry_is_authoritative(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, _b, _c = repo(root, lambda r, b, c: body())
            (root / 'requirements.json').write_text(json.dumps({'required_gate_ids': ['spec', 'extra']}), encoding='utf-8')
            self.assertIn('gate_missing', checks(manifest, root))

    def test_scope_escalation_no_longer_disables_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            def mutate(r, b, c):
                payload = body()
                payload['scope'] = 'production'
                payload['claims'][0]['statement'] = 'production ready'
                return payload
            manifest, _b, _c = repo(root, mutate)
            code = checks(manifest, root)
            self.assertIn('production_unbound', code)
            self.assertIn('claim_production_wording', code)

    def test_production_requires_readable_true_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            def mutate(r, b, c):
                payload = body()
                payload['scope'] = 'production'
                payload['production_evidence'] = {'acceptance_status_path': 'spec/acceptance.status.json',
                                                  'acceptance_status_sha256': 'c' * 64,
                                                  'release_gate_path': 'gate.json',
                                                  'release_gate_sha256': 'd' * 64}
                return payload
            manifest, _b, _c = repo(root, mutate)
            self.assertIn('production_unbound', checks(manifest, root))

    def test_self_signed_and_boolean_spoofing_still_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            def mutate(r, b, c):
                payload = body()
                payload['reviewed_by']['reviewer_id'] = payload['reviewed_by']['implementer_id']
                payload['reviewed_by']['independent'] = 1
                return payload
            manifest, _b, _c = repo(root, mutate)
            code = checks(manifest, root)
            self.assertIn('review_self_signed', code)
            self.assertIn('review_not_independent', code)


if __name__ == '__main__':
    unittest.main()