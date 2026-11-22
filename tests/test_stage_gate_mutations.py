"""Mutation killers for the stage manifest gate (schema v3 + external pins)."""
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

GATE = pathlib.Path(__file__).resolve().parents[1] / 'scripts/stage_gate.py'
PAST = '2020-01-01T00:00:00Z'

MUTANTS = [
    ('skip_manifest_pin', "if type(manifest_pin) is not str or type(manifest['manifest_sha256']) is not str or manifest_pin != manifest['manifest_sha256']:", 'if False:'),
    ('skip_requirements_pin', "if type(pinned) is not str or hashlib.sha256(payload).hexdigest() != pinned:", 'if False:'),
    ('skip_anchor_contained', "if git(root, 'merge-base', '--is-ancestor', manifest['candidate_sha'], ref).returncode != 0:", 'if False:'),
    ('skip_failure_text', 'if marker in lowered_body:', 'if False:'),
    ('skip_window_early', 'if start_at < committed_at:', 'if False:'),
    ('skip_naive_window', 'if start_at.tzinfo is None or end_at.tzinfo is None:', 'if False:'),
    ('skip_ref_prefix', "if not ref.startswith(('refs/remotes/', 'refs/tags/')):", 'if False:'),
    ('skip_ref_sha', 'if type(pin_ref) is not str or pin_ref != tip:', 'if False:'),
    ('skip_base_in_ref', "if git(root, 'merge-base', '--is-ancestor', manifest['base_sha'], ref).returncode != 0:", 'if False:'),
    ('skip_drift', 'if other is None or other != payload:', 'if False:'),
    ('skip_result_line', "if not lines or lines[-1] != 'RESULT: PASS gate=' + gid + ' exit=0':", 'if False:'),
    ('skip_attestation_required', "out.append(('attestation_missing', 'no signed attestation supplied'))", 'pass'),
    ('skip_attestation_signature', "if not attestation_valid:", 'if False:'),
    ('skip_trusted_key', "if type(key) is not str or HEX64.match(key.lower()) is None or key.lower() not in trusted:", 'if False:'),
    ('skip_review_signature', 'if not review_valid:', 'if False:'),
    ('skip_production_committed', 'if payload is None:', 'if False:'),
    ('skip_production_malformed', "if type(gate_state) is not dict or type(gate_state.get('production')) is not dict:", 'if False:'),
]

KINDS = {'skip_manifest_pin': 'pin', 'skip_requirements_pin': 'reqpin', 'skip_anchor_contained': 'anchor',
         'skip_failure_text': 'failed', 'skip_window_early': 'early', 'skip_naive_window': 'naive',
         'skip_ref_prefix': 'localref', 'skip_ref_sha': 'movedref', 'skip_base_in_ref': 'baseout',
         'skip_drift': 'drift', 'skip_result_line': 'noresult', 'skip_attestation_required': 'noattest',
         'skip_attestation_signature': 'forged', 'skip_trusted_key': 'strangerkey',
         'skip_review_signature': 'reviewsig', 'skip_production_committed': 'prodcommitted',
         'skip_production_malformed': 'prodmalformed'}
EXPECTED = {'skip_manifest_pin': 'manifest_unpinned', 'skip_requirements_pin': 'requirements_unpinned',
            'skip_anchor_contained': 'anchor_not_contained', 'skip_failure_text': 'evidence_failure_text',
            'skip_window_early': 'review_window_early', 'skip_naive_window': 'review_window_naive',
            'skip_ref_prefix': 'anchor_ref_invalid', 'skip_ref_sha': 'anchor_ref_moved',
            'skip_base_in_ref': 'anchor_base_outside_ref', 'skip_drift': 'requirements_drift',
            'skip_result_line': 'evidence_result_missing',
            'skip_attestation_required': 'attestation_missing',
            'skip_attestation_signature': 'attestation_bad_signature',
            'skip_trusted_key': 'attestation_untrusted_key',
            'skip_review_signature': 'review_bad_signature',
            'skip_production_committed': 'production_uncommitted',
            'skip_production_malformed': 'production_malformed'}


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace')


def write_lf(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        handle.write(text)


def commit(root, message):
    git(root, 'add', '-A')
    env = dict(os.environ, GIT_AUTHOR_DATE=PAST, GIT_COMMITTER_DATE=PAST)
    subprocess.run(['git', '-c', 'user.email=t@e', '-c', 'user.name=t', 'commit', '-q', '-m', message],
                   cwd=root, capture_output=True, env=env)


def build(root, module, kind):
    root.mkdir(parents=True, exist_ok=True)
    git(root, 'init', '-q')
    write_lf(root / 'requirements.json', json.dumps({'required_gate_ids': ['spec'], 'min_level': 'I2'}))
    body_text = 'FAILED (3 errors)' if kind == 'failed' else 'ok'
    header = json.dumps({'gate': 'spec', 'command': 'cmd', 'exit_code': 0}, sort_keys=True)
    tail = '' if kind == 'noresult' else ('RESULT: PASS gate=spec exit=0' + chr(10))
    write_lf(root / 'evidence/spec.log', header + chr(10) + body_text + chr(10) + tail)
    commit(root, 'one')
    base = git(root, 'rev-parse', 'HEAD').stdout.strip()
    write_lf(root / 'notes.txt', 'n' + chr(10))
    commit(root, 'two')
    candidate = git(root, 'rev-parse', 'HEAD').stdout.strip()
    git(root, 'update-ref', 'refs/remotes/origin/main', candidate)
    requirements_sha = hashlib.sha256(module.committed_bytes(root, base, 'requirements.json')).hexdigest()
    window_start = '2019-01-01T00:00:00Z' if kind == 'early' else '2026-01-01T00:00:00Z'
    window_end = '2019-01-02T00:00:00Z' if kind == 'early' else '2026-01-02T00:00:00Z'
    if kind == 'naive':
        window_start = '2026-01-01T00:00:00'
        window_end = '2026-01-02T00:00:00'
    review_seed = bytes(range(32, 64))
    review_public = module.ed25519_module().public_key(review_seed)
    payload = {
        'schema': 'stage-manifest/3',
        'stage_id': 'stage-x',
        'candidate_sha': candidate,
        'base_sha': base,
        'scope': 'isolated',
        'required_min_level': 'I2',
        'gates': [{'id': 'spec', 'command': 'cmd', 'exit_code': 0, 'raw_log': 'evidence/spec.log',
                   'raw_log_sha256': hashlib.sha256((root / 'evidence/spec.log').read_bytes()).hexdigest(),
                   'independence': 'I2', 'status': 'PASS'}],
        'claims': [{'id': 'c', 'statement': 'tools pass', 'level': 'I2', 'scope': 'isolated', 'gate_ids': ['spec']}],
        'not_claimed': ['production', 'm6-migration'],
        'reviewed_by': {'implementer_id': 'i', 'reviewer_id': 'v', 'role': 'independent-verifier',
                        'independent': True, 'session': 's', 'window_start': window_start,
                        'window_end': window_end, 'reviewer_keyid': review_public.hex(),
                        'signature': ''},
    }
    projection = dict(payload)
    reviewed = {key: value for key, value in projection['reviewed_by'].items() if key != 'signature'}
    reviewed['reviewer_keyid'] = review_public.hex()
    projection['reviewed_by'] = reviewed
    payload['reviewed_by']['signature'] = module.ed25519_module().sign(
        review_seed, module.canonical(projection)).hex()
    if kind == 'reviewsig':
        payload['claims'][0]['statement'] = 'tampered after signing'
    manifest = module.build_manifest(payload)
    pins = {'manifest_sha256': manifest['manifest_sha256'],
            'requirements_sha256': requirements_sha,
            'require_ref': 'refs/remotes/origin/main',
            'ref_sha': candidate,
            'reviewer_keys': [review_public]}
    if kind == 'pin':
        pins['manifest_sha256'] = ''
    elif kind == 'reqpin':
        pins['requirements_sha256'] = 'f' * 64
    elif kind == 'anchor':
        git(root, 'update-ref', 'refs/remotes/origin/main', base)
    elif kind == 'localref':
        pins['require_ref'] = 'refs/heads/master'
    elif kind == 'movedref':
        pins['ref_sha'] = base
    elif kind == 'baseout':
        git(root, 'checkout', '-q', '--orphan', 'solo')
        commit(root, 'solo')
        manifest['base_sha'] = git(root, 'rev-parse', 'HEAD').stdout.strip()
    elif kind == 'drift':
        write_lf(root / 'requirements.json', json.dumps({'required_gate_ids': ['spec', 'zzz'], 'min_level': 'I2'}))
    if kind in ('noattest', 'forged', 'strangerkey'):
        import scripts.ed25519 as signer
        seed = bytes(range(32))
        public = signer.public_key(seed)
        body = {'manifest_sha256': manifest['manifest_sha256'],
                'requirements_sha256': requirements_sha,
                'ref': 'refs/remotes/origin/main',
                'ref_sha': candidate,
                'issuer': 'reviewer',
                'issued_at': '2026-01-01T00:30:00Z',
                'public_key': public.hex()}
        signature = signer.sign(seed, module.canonical(body)).hex()
        if kind == 'forged':
            signature = '00' * 64
        record = dict(body, signature=signature)
        path = root / 'attestation.json'
        write_lf(path, json.dumps(record, sort_keys=True))
        if kind == 'noattest':
            pins['attestation_path'] = ''
        else:
            pins['attestation_path'] = str(path)
            pins['trusted_keys'] = [public.hex().lower()] if kind == 'forged' else ['ab' * 32]
    return manifest, pins


class StageGateMutationTests(unittest.TestCase):
    def test_every_pinned_check_is_load_bearing(self):
        original = GATE.read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as tmp:
            for name, old, new in MUTANTS:
                with self.subTest(name=name):
                    self.assertIn(old, original, 'anchor missing: ' + name)
                    work = pathlib.Path(tmp) / name
                    work.mkdir()
                    mutant = work / 'stage_gate.py'
                    mutant.write_text(original.replace(old, new, 1), encoding='utf-8')
                    shutil.copy(GATE.with_name('ed25519.py'), work / 'ed25519.py')
                    spec = importlib.util.spec_from_file_location('_gate_mut', mutant)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    repo_dir = work / 'repo'
                    manifest, pins = build(repo_dir, module, KINDS[name])
                    try:
                        reported = [c for c, _d in module.validate(manifest, repo_dir, pins)]
                    except Exception as error:
                        reported = ['exception:' + type(error).__name__]
                    self.assertNotIn(EXPECTED[name], reported, 'mutant survived: ' + name)


if __name__ == '__main__':
    unittest.main()