"""Mutation killers for the stage manifest gate (schema v3)."""
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest

GATE = pathlib.Path(__file__).resolve().parents[1] / 'scripts/stage_gate.py'

MUTANTS = [
    ('skip_status', "if gate['status'] != 'PASS':", 'if False:'),
    ('skip_exit', "if type(gate['exit_code']) is not int or gate['exit_code'] != 0:", 'if False:'),
    ('skip_blob_sha', "if type(stored) is not str or HEX64.match(stored) is None or hashlib.sha256(payload).hexdigest() != stored:", 'if False:'),
    ('skip_header', 'if header is None:', 'if False:'),
    ('skip_header_match', "if header['gate'] != gid or header['command'] != gate['command'] or header['exit_code'] != gate['exit_code']:", 'if False:'),
    ('skip_evidence_prefix', "if not raw.startswith(EVIDENCE_PREFIX) or raw.endswith('.json') or raw.startswith(FORBIDDEN_PREFIX):", 'if False:'),
    ('skip_reuse', 'if raw in seen:', 'if False:'),
    ('skip_gate_missing', 'for gid in sorted(set(required) - set(levels)):', 'for gid in []:'),
    ('skip_digest', "if type(manifest['manifest_sha256']) is not str or digest(body) != manifest['manifest_sha256']:", 'if False:'),
    ('skip_self_signed', 'elif implementer == verifier:', 'elif False:'),
    ('skip_wording', 'if word in lowered:', 'if False:'),
    ('skip_production_files', "if hashlib.sha256(path.read_bytes()).hexdigest() != evidence[key_sha]:", 'if False:'),
]

KINDS = {
    'skip_status': 'status', 'skip_exit': 'exit', 'skip_blob_sha': 'blob', 'skip_header': 'header',
    'skip_header_match': 'header', 'skip_evidence_prefix': 'prefix', 'skip_reuse': 'reuse',
    'skip_gate_missing': 'required', 'skip_digest': 'digest', 'skip_self_signed': 'self',
    'skip_wording': 'wording', 'skip_production_files': 'production',
}

EXPECTED = {
    'skip_status': 'gate_not_run', 'skip_exit': 'gate_exit', 'skip_blob_sha': 'gate_raw_sha',
    'skip_header': 'evidence_header', 'skip_header_match': 'evidence_mismatch',
    'skip_evidence_prefix': 'gate_raw_path', 'skip_reuse': 'gate_raw_reused',
    'skip_gate_missing': 'gate_missing', 'skip_digest': 'manifest_digest',
    'skip_self_signed': 'review_self_signed', 'skip_wording': 'claim_production_wording',
    'skip_production_files': 'production_unbound',
}


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace')


def build(root, module, kind):
    root.mkdir(parents=True, exist_ok=True)
    git(root, 'init', '-q')
    ev = root / 'evidence/spec.log'
    ev.parent.mkdir(parents=True, exist_ok=True)
    header = {'gate': 'spec', 'command': 'cmd', 'exit_code': 0}
    if kind == 'header':
        header = {'gate': 'spec', 'command': 'cmd'}
    if kind == 'header_match':
        header = {'gate': 'other', 'command': 'cmd', 'exit_code': 0}
    with ev.open('w', encoding='utf-8', newline='') as handle:
        handle.write(json.dumps(header, sort_keys=True) + chr(10) + 'body' + chr(10))
    (root / 'notes.txt').write_text('n1' + chr(10), encoding='utf-8')
    git(root, 'add', '-A')
    subprocess.run(['git', '-c', 'user.email=t@e', '-c', 'user.name=t', 'commit', '-q', '-m', 'one'], cwd=root, capture_output=True)
    base = git(root, 'rev-parse', 'HEAD').stdout.strip()
    (root / 'notes.txt').write_text('n2' + chr(10), encoding='utf-8')
    git(root, 'add', '-A')
    subprocess.run(['git', '-c', 'user.email=t@e', '-c', 'user.name=t', 'commit', '-q', '-m', 'two'], cwd=root, capture_output=True)
    candidate = git(root, 'rev-parse', 'HEAD').stdout.strip()
    payload = {
        'schema': 'stage-manifest/3',
        'stage_id': 'stage-x',
        'candidate_sha': candidate,
        'base_sha': base,
        'scope': 'isolated',
        'required_min_level': 'I2',
        'gates': [{'id': 'spec', 'command': 'cmd', 'exit_code': 0, 'raw_log': 'evidence/spec.log',
                   'raw_log_sha256': hashlib.sha256(ev.read_bytes()).hexdigest(),
                   'independence': 'I2', 'status': 'PASS'}],
        'claims': [{'id': 'c', 'statement': 'tools pass', 'level': 'I2', 'scope': 'isolated', 'gate_ids': ['spec']}],
        'not_claimed': ['production', 'm6-migration'],
        'reviewed_by': {'implementer_id': 'i', 'reviewer_id': 'v', 'role': 'independent-verifier',
                        'independent': True, 'session': 's', 'window_start': '2026-01-01T00:00:00Z',
                        'window_end': '2026-01-01T01:00:00Z'},
    }
    if kind == 'status':
        payload['gates'][0]['status'] = 'NOT_RUN'
    elif kind == 'exit':
        payload['gates'][0]['exit_code'] = 2
    elif kind == 'blob':
        ev.write_text('tampered' + chr(10), encoding='utf-8')
    elif kind == 'prefix':
        payload['gates'][0]['raw_log'] = 'notes.txt'
    elif kind == 'reuse':
        payload['gates'].append(dict(payload['gates'][0], id='spec2'))
    elif kind == 'required':
        pass
    elif kind == 'digest':
        payload['required_min_level'] = 'I1'
    elif kind == 'self':
        payload['reviewed_by']['reviewer_id'] = 'i'
    elif kind == 'wording':
        payload['claims'][0]['statement'] = 'production ready'
    elif kind == 'production':
        payload['scope'] = 'production'
        gate_file = root / 'gate.json'
        acc_file = root / 'acc.json'
        with gate_file.open('w', encoding='utf-8', newline='') as handle:
            handle.write(json.dumps({'production': {'state': 'PASS'}}))
        with acc_file.open('w', encoding='utf-8', newline='') as handle:
            handle.write(json.dumps({'production': 'PASS'}))
        payload['production_evidence'] = {'acceptance_status_path': 'acc.json',
                                          'acceptance_status_sha256': 'c' * 64,
                                          'release_gate_path': 'gate.json',
                                          'release_gate_sha256': 'd' * 64}
    built = {k: v for k, v in payload.items() if k != 'manifest_sha256'}
    return module.build_manifest(built)


class StageGateMutationTests(unittest.TestCase):
    def test_every_gate_check_is_load_bearing(self):
        original = GATE.read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as tmp:
            for name, old, new in MUTANTS:
                with self.subTest(name=name):
                    self.assertIn(old, original, 'anchor missing: ' + name)
                    work = pathlib.Path(tmp) / name
                    work.mkdir()
                    mutant = work / 'stage_gate.py'
                    mutant.write_text(original.replace(old, new, 1), encoding='utf-8')
                    spec = importlib.util.spec_from_file_location('_gate_mut', mutant)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    kind = KINDS[name]
                    repo_dir = work / 'repo'
                    manifest = build(repo_dir, module, kind)
                    requirements = {'required_gate_ids': ['spec'] if kind != 'required' else ['spec', 'absent']}
                    try:
                        reported = [c for c, _d in module.validate(manifest, repo_dir, requirements)]
                    except Exception as error:
                        reported = ['exception:' + type(error).__name__]
                    self.assertNotIn(EXPECTED[name], reported, 'mutant survived: ' + name)


if __name__ == '__main__':
    unittest.main()