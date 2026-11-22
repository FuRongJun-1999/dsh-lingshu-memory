"""Independent expectations for the stage manifest gate (schema v3, external pins, v5 hardening)."""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from framework.spec import ROOT
import scripts.ed25519 as signer
import scripts.stage_gate as gate_mod
SEED = bytes(range(32))
REVIEW_SEED = bytes(range(32, 64))

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


def evidence(root, gate='spec', command='python scripts/check_all.py', exit_code=0, body='ok', result=True):
    path = root / 'evidence' / (gate + '.log')
    header = json.dumps({'gate': gate, 'command': command, 'exit_code': exit_code}, sort_keys=True)
    tail = ('RESULT: PASS gate=' + gate + ' exit=0') if result else ''
    write_lf(path, header + chr(10) + body + chr(10) + tail + chr(10))
    return path


def sign_review(body):
    projection = dict(body)
    reviewed = {key: value for key, value in projection['reviewed_by'].items() if key != 'signature'}
    reviewed['reviewer_keyid'] = signer.public_key(REVIEW_SEED).hex()
    projection['reviewed_by'] = reviewed
    body['reviewed_by']['reviewer_keyid'] = reviewed['reviewer_keyid']
    body['reviewed_by']['signature'] = signer.sign(REVIEW_SEED, gate_mod.canonical(projection)).hex()


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
                        'window_end': WINDOW_END, 'reviewer_keyid': signer.public_key(REVIEW_SEED).hex(),
                        'signature': '0' * 128},
    }
    if mutate is not None:
        mutate(body)
    sign_review(body)
    manifest = gate_mod.build_manifest(body)
    return manifest


def setup(root, mutate=None, requirements_in_base=True, ref='refs/remotes/origin/main'):
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
    git(root, 'update-ref', ref, candidate)
    committed = gate_mod.committed_bytes(root, base, 'requirements.json')
    requirements_sha = hashlib.sha256(committed).hexdigest() if committed is not None else '0' * 64
    manifest = payload(root, base, candidate, requirements_sha, mutate)
    pins = {'manifest_sha256': manifest['manifest_sha256'],
            'requirements_sha256': requirements_sha,
            'require_ref': ref,
            'ref_sha': candidate,
            'reviewer_keys': [signer.public_key(REVIEW_SEED).hex()]}
    return manifest, pins


def attestation(manifest, pins, *, key=SEED, tamper=None, trusted=True):
    public = signer.public_key(key)
    body = {'manifest_sha256': manifest['manifest_sha256'],
            'requirements_sha256': pins['requirements_sha256'],
            'ref': pins['require_ref'],
            'ref_sha': pins['ref_sha'],
            'issuer': 'stage-reviewer',
            'issued_at': '2026-01-01T00:30:00Z',
            'public_key': public.hex()}
    signature = signer.sign(key, gate_mod.canonical(body))
    record = dict(body, signature=signature.hex())
    if tamper == 'manifest':
        body['manifest_sha256'] = 'e' * 64
        record = dict(body, signature=signer.sign(key, gate_mod.canonical(body)).hex())
    elif tamper == 'signature':
        record['signature'] = ('00' * 64)
    elif tamper == 'time':
        body['issued_at'] = '2099-01-01T00:00:00Z'
        record = dict(body, signature=signer.sign(key, gate_mod.canonical(body)).hex())
    root = pins.pop('_root')
    path = root / 'attestation.json'
    write_lf(path, json.dumps(record, sort_keys=True))
    pins['attestation_path'] = str(path)
    pins['trusted_keys'] = [public.hex().lower()] if trusted else ['ab' * 32]
    return path


def codes(manifest, root, pins):
    pins = dict(pins)
    pins['_root'] = root
    if pins.get('attestation', True):
        attestation(manifest, pins, tamper=pins.get('tamper'), trusted=pins.get('trusted', True))
    pins.pop('_root', None)
    pins.pop('attestation', None)
    pins.pop('tamper', None)
    pins.pop('trusted', None)
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
            git(root, 'update-ref', 'refs/remotes/origin/main', manifest['base_sha'])
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
            git(root, 'update-ref', 'refs/remotes/origin/main', candidate)
            committed = gate_mod.committed_bytes(root, base, 'requirements.json')
            requirements_sha = hashlib.sha256(committed).hexdigest() if committed is not None else '0' * 64
            manifest = payload(root, base, candidate, requirements_sha)
            pins = {'manifest_sha256': manifest['manifest_sha256'], 'requirements_sha256': requirements_sha,
                    'require_ref': 'refs/remotes/origin/main', 'ref_sha': candidate,
                    'reviewer_keys': [signer.public_key(REVIEW_SEED).hex()], 'attestation': False}
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
                                     '--require-ref', 'refs/remotes/origin/main',
                                     '--pin-ref-sha', pins['ref_sha'],
                                     '--reviewer-key', signer.public_key(REVIEW_SEED).hex(),
                                     '--allow-weak-pin'],
                                    cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(pinned.returncode, 0, pinned.stdout + pinned.stderr)



class StageGateHardeningTests(unittest.TestCase):
    def test_naive_window_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            def mutate(body):
                body['reviewed_by']['window_start'] = '2026-01-01T00:00:00'
                body['reviewed_by']['window_end'] = '2026-01-02T00:00:00'
            manifest, pins = setup(root, mutate)
            self.assertIn('review_window_naive', codes(manifest, root, pins))

    def test_local_branch_ref_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            pins['require_ref'] = 'refs/heads/main'
            self.assertIn('anchor_ref_invalid', codes(manifest, root, pins))

    def test_moved_ref_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            pins['ref_sha'] = manifest['base_sha']
            self.assertIn('anchor_ref_moved', codes(manifest, root, pins))

    def test_base_outside_ref_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            orphan = root / 'orphan.txt'
            write_lf(orphan, 'x' + chr(10))
            git(root, 'checkout', '-q', '--orphan', 'other')
            commit_all(root, 'orphan root')
            other = git(root, 'rev-parse', 'HEAD').stdout.strip()
            manifest['base_sha'] = other
            self.assertIn('anchor_base_outside_ref', codes(manifest, root, pins))

    def test_requirements_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            write_lf(root / 'requirements.json', json.dumps({'required_gate_ids': ['spec', 'zzz'], 'min_level': 'I2'}))
            commit_all(root, 'drifted registry')
            drifted = git(root, 'rev-parse', 'HEAD').stdout.strip()
            git(root, 'update-ref', 'refs/remotes/origin/main', drifted)
            manifest['candidate_sha'] = drifted
            pins['ref_sha'] = drifted
            self.assertIn('requirements_drift', codes(manifest, root, pins))

    def test_missing_result_line_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            git(root, 'init', '-q')
            write_lf(root / 'requirements.json', json.dumps({'required_gate_ids': ['spec'], 'min_level': 'I2'}))
            evidence(root, result=False)
            commit_all(root, 'one')
            base = git(root, 'rev-parse', 'HEAD').stdout.strip()
            write_lf(root / 'notes.txt', 'n' + chr(10))
            commit_all(root, 'two')
            candidate = git(root, 'rev-parse', 'HEAD').stdout.strip()
            git(root, 'update-ref', 'refs/remotes/origin/main', candidate)
            committed = gate_mod.committed_bytes(root, base, 'requirements.json')
            requirements_sha = hashlib.sha256(committed).hexdigest()
            manifest = payload(root, base, candidate, requirements_sha)
            pins = {'manifest_sha256': manifest['manifest_sha256'], 'requirements_sha256': requirements_sha,
                    'require_ref': 'refs/remotes/origin/main', 'ref_sha': candidate}
            self.assertIn('evidence_result_missing', codes(manifest, root, pins))



class StageGateAttestationTests(unittest.TestCase):
    def test_signed_attestation_enables_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            self.assertEqual(codes(manifest, root, pins), [])

    def test_missing_attestation_blocks_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            pins['attestation'] = False
            self.assertIn('attestation_missing', codes(manifest, root, pins))

    def test_untrusted_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            pins['trusted'] = False
            self.assertIn('attestation_untrusted_key', codes(manifest, root, pins))

    def test_tampered_manifest_digest_breaks_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            pins['tamper'] = 'manifest'
            self.assertIn('attestation_mismatch', codes(manifest, root, pins))

    def test_forged_signature_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            pins['tamper'] = 'signature'
            self.assertIn('attestation_bad_signature', codes(manifest, root, pins))

    def test_future_issued_at_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            pins['tamper'] = 'time'
            self.assertIn('attestation_time', codes(manifest, root, pins))



class StageGateReviewSignatureTests(unittest.TestCase):
    def test_signed_review_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            manifest['reviewed_by']['signature'] = ''
            self.assertIn('review_bad_signature', codes(manifest, root, pins))

    def test_untrusted_reviewer_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            pins['reviewer_keys'] = ['ab' * 32]
            self.assertIn('review_key_untrusted', codes(manifest, root, pins))

    def test_tampered_gate_list_breaks_review_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = setup(root)
            manifest['gates'][0]['status'] = 'PASS'
            manifest['claims'][0]['statement'] = 'tools pass, reviewed'
            self.assertIn('review_bad_signature', codes(manifest, root, pins))



class StageGateEvidencePathTests(unittest.TestCase):
    def test_absolute_evidence_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            def mutate(body):
                body['gates'][0]['raw_log'] = 'C:/tmp/x.log'
            manifest, pins = setup(root, mutate)
            self.assertIn('gate_raw_path', codes(manifest, root, pins))

    def test_parent_traversal_evidence_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            def mutate(body):
                body['gates'][0]['raw_log'] = 'evidence/../notes.txt'
            manifest, pins = setup(root, mutate)
            self.assertIn('gate_raw_path', codes(manifest, root, pins))

    def test_json_evidence_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            def mutate(body):
                body['gates'][0]['raw_log'] = 'evidence/spec.json'
            manifest, pins = setup(root, mutate)
            self.assertIn('gate_raw_path', codes(manifest, root, pins))

    def test_script_prefix_evidence_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            def mutate(body):
                body['gates'][0]['raw_log'] = 'scripts/spec.log'
            manifest, pins = setup(root, mutate)
            self.assertIn('gate_raw_path', codes(manifest, root, pins))



class StageGateProductionEvidenceTests(unittest.TestCase):
    def _production_manifest(self, root, acceptance, gate_state, declared=None):
        manifest, pins = setup(root)
        write_lf(root / 'acc.json', json.dumps(acceptance))
        write_lf(root / 'gate.json', json.dumps(gate_state))
        commit_all(root, 'production evidence')
        tip = git(root, 'rev-parse', 'HEAD').stdout.strip()
        git(root, 'update-ref', 'refs/remotes/origin/main', tip)
        manifest['scope'] = 'production'
        manifest['candidate_sha'] = tip
        pins['ref_sha'] = tip
        manifest['production_evidence'] = {
            'acceptance_status_path': 'acc.json',
            'acceptance_status_sha256': declared[0] if declared else hashlib.sha256((root / 'acc.json').read_bytes()).hexdigest(),
            'release_gate_path': 'gate.json',
            'release_gate_sha256': declared[1] if declared else hashlib.sha256((root / 'gate.json').read_bytes()).hexdigest(),
        }
        rebuilt = {k: v for k, v in manifest.items() if k != 'manifest_sha256'}
        manifest = gate_mod.build_manifest(rebuilt)
        pins['manifest_sha256'] = manifest['manifest_sha256']
        return manifest, pins

    def test_committed_production_evidence_can_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = self._production_manifest(root, {'production': 'PASS'}, {'production': {'state': 'PASS'}})
            code = codes(manifest, root, pins)
            self.assertNotIn('production_unbound', code)
            self.assertNotIn('production_uncommitted', code)

    def test_working_tree_only_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = self._production_manifest(root, {'production': 'PASS'}, {'production': {'state': 'PASS'}})
            write_lf(root / 'acc.json', json.dumps({'production': 'PASS', 'note': 'uncommitted edit'}))
            manifest['production_evidence']['acceptance_status_sha256'] = hashlib.sha256((root / 'acc.json').read_bytes()).hexdigest()
            rebuilt = {k: v for k, v in manifest.items() if k != 'manifest_sha256'}
            manifest = gate_mod.build_manifest(rebuilt)
            pins['manifest_sha256'] = manifest['manifest_sha256']
            self.assertIn('production_unbound', codes(manifest, root, pins))

    def test_malformed_production_evidence_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = self._production_manifest(root, {'production': 'PASS'}, {'production': 'PASS'})
            self.assertIn('production_malformed', codes(manifest, root, pins))

    def test_production_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest, pins = self._production_manifest(root, {'production': 'PASS'}, {'production': {'state': 'PASS'}})
            manifest['production_evidence']['acceptance_status_path'] = '../acc.json'
            rebuilt = {k: v for k, v in manifest.items() if k != 'manifest_sha256'}
            manifest = gate_mod.build_manifest(rebuilt)
            pins['manifest_sha256'] = manifest['manifest_sha256']
            self.assertIn('production_path_invalid', codes(manifest, root, pins))


if __name__ == '__main__':
    unittest.main()