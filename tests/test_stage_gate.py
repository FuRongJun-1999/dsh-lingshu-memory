"""Independent expectations for the stage manifest gate (schema v3 + external pins)."""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from framework.spec import ROOT
import scripts.stage_gate as gate_mod

PAST = '2020-01-01T00:00:00Z'
WINDOW_START = '2026-01-01T00:00:00Z'
WINDOW_END = '2026-01-02T00:00:00Z'


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace')


def write_lf(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        handle.write(text)


def commit_all(root, message):
    git(root, 'add', '-A')
    env = {'GIT_AUTHOR_DATE': PAST, 'GIT_COMMITTER_DATE': PAST}
    env.update({k: v for k, v in __import__('os').environ.items()})
    result = subprocess.run(['git', '-c', 'user.email=t@example.invalid', '-c', 'user.name=t',
                             'commit', '-q', '-m', message], cwd=root, capture_output=True, text=True,
                            encoding='utf-8', env=env)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)


def evidence(root, gate='spec', command='python scripts/check_all.py', exit_code=0, body='ok'):
    path = root / 'evidence' / (gate + '.log')
    header = json.dumps({'gate': gate, 'command': command, 'exit_code': exit_code}, sort_keys=True)
    write_lf(path, header + chr(10) + body + chr(10))
    return path


def payload(root, base, candidate, requirements_sha, mutate=None):
    body = {
        'schema': 'stage-manifest/3',
        'stage_id': 'stage-0.2',
        'candidate_sha': candidate,
        'base_sha': base,
        'scope': 'isolated',
        'required_min_level': 'I2',
        'gates': [{'id': 'spec', 'command': 'python scripts/check_all.py', 'exit_code': 0,
                   'raw_log': 'evidence/spec.log',
                   'raw_log_sha256': hashlib.sha256((root / 'evidence/spec.log').read_bytes()).hexdigest(),
                   'independence': 'I2', 'status': 'PASS'}],
        'claims': [{'id': 'spec-tools', 'statement': 'specification tools pass', 'level': 'I2',
                    'scope': 'isolated', 'gate_ids': ['spec']}],
        'not_claimed': ['production', 'm6-migration'],
        'reviewed_by': {'implementer_id': 'impl', 'reviewer_id': 'ver', 'role': 'independent-verifier',
                        'independent': True, 'session': 's', 'window_start': WINDOW_START,
                        'window_end': WINDOW_END},
    }
    if mutate is not None:
        mutate(body)
    manifest = gate_mod.build_manifest(body)
    return manifest


def setup(root, mutate=None, requirements_in_base=True, ref='refs/heads/trunk'):
    git(root, 'init', '-q')
    evidence(root)
    if requirements_in_base:
        write_lf(root / 'requirements.json', json.dumps({'required_gate_ids': ['spec'], 'min_level': 'I2'}))
    write_lf(root / 'notes.txt', 'n1' + chr(10))
    commit_all(root, 'one')
    base = git(root, 'rev-parse', 'HEAD').stdout.strip()
    if not requirements_in_base:
        write_lf(root / 'requirements.json', json.dumps({'required_gate_ids': ['spec'], 'min_level': 'I2'}))
    write_lf(root / 'notes.txt', 'n2' + chr(10))
    commit_all(root, 'two')
    candidate = git(root, 'rev-parse', 'HEAD').stdout.strip()
    git(root, 'branch', '-f', 'trunk', candidate)
    committed = gate_mod.committed_bytes(root, base, 'requirements.json')
    requirements_sha = hashlib.sha256(committed).hexdigest() if committed is not None else '0' * 64
    manifest = payload(root, base, candidate, requirements_sha, mutate)
    pins = {'manifest_sha256': manifest['manifest_sha256'],
            'requirements_sha256': requirements_sha,
            'require_ref': ref}
    return manifest, pins


def codes(manifest, root, pins):
    return [code for code, _detail in gate_mod.validate(manifest, root, pins)]


class StageGatePinnedTests(unittest.TestCase):
    def test_pinned_manifest_with_committed_requirements_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            self.assertEqual(codes(manifest, root, pins), [])

    def test_missing_manifest_pin_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            pins['manifest_sha256'] = ''
            self.assertIn('manifest_unpinned', codes(manifest, root, pins))

    def test_wrong_requirements_pin_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            pins['requirements_sha256'] = 'f' * 64
            self.assertIn('requirements_unpinned', codes(manifest, root, pins))

    def test_requirements_must_exist_in_base_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root, requirements_in_base=False)
            self.assertIn('requirements_uncommitted', codes(manifest, root, pins))

    def test_candidate_must_be_contained_in_pinned_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            git(root, 'branch', '-f', 'trunk', manifest['base_sha'])
            self.assertIn('anchor_not_contained', codes(manifest, root, pins))

    def test_missing_external_ref_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root, ref='')
            self.assertIn('anchor_ref_missing', codes(manifest, root, pins))

    def test_failed_log_body_is_rejected_even_with_matching_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            def mutate(body):
                pass
            git(root, 'init', '-q')
            write_lf(root / 'requirements.json', json.dumps({'required_gate_ids': ['spec'], 'min_level': 'I2'}))
            evidence(root, body='FAILED (3 errors)')
            commit_all(root, 'one')
            base = git(root, 'rev-parse', 'HEAD').stdout.strip()
            write_lf(root / 'notes.txt', 'n' + chr(10))
            commit_all(root, 'two')
            candidate = git(root, 'rev-parse', 'HEAD').stdout.strip()
            git(root, 'branch', '-f', 'trunk', candidate)
            committed = gate_mod.committed_bytes(root, base, 'requirements.json')
            requirements_sha = hashlib.sha256(committed).hexdigest() if committed is not None else '0' * 64
            manifest = payload(root, base, candidate, requirements_sha)
            pins = {'manifest_sha256': manifest['manifest_sha256'], 'requirements_sha256': requirements_sha,
                    'require_ref': 'refs/heads/trunk'}
            self.assertIn('evidence_failure_text', codes(manifest, root, pins))

    def test_window_before_candidate_commit_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            def mutate(body):
                body['reviewed_by']['window_start'] = '2019-01-01T00:00:00Z'
                body['reviewed_by']['window_end'] = '2019-01-02T00:00:00Z'
            manifest, pins = setup(root, mutate)
            self.assertIn('review_window_early', codes(manifest, root, pins))

    def test_future_window_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            def mutate(body):
                body['reviewed_by']['window_start'] = '2099-01-01T00:00:00Z'
                body['reviewed_by']['window_end'] = '2099-01-02T00:00:00Z'
            manifest, pins = setup(root, mutate)
            self.assertIn('review_window_future', codes(manifest, root, pins))

    def test_cli_requires_pins_to_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            path = root / 'manifest.json'
            write_lf(path, json.dumps(manifest, sort_keys=True))
            bare = subprocess.run([sys.executable, '-B', 'scripts/stage_gate.py', '--manifest', str(path)],
                                  cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(bare.returncode, 1)
            self.assertIn('manifest_unpinned', bare.stdout)
            pinned = subprocess.run([sys.executable, '-B', 'scripts/stage_gate.py', '--manifest', str(path),
                                     '--pin-manifest-sha256', pins['manifest_sha256'],
                                     '--pin-requirements-sha256', pins['requirements_sha256'],
                                     '--require-ref', 'refs/heads/trunk'],
                                    cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(pinned.returncode, 0, pinned.stdout + pinned.stderr)


if __name__ == '__main__':
    unittest.main()