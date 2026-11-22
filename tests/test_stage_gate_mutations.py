"""Mutation killers for the stage manifest gate (schema v2)."""
import hashlib
import importlib.util
import pathlib
import tempfile
import unittest

GATE = pathlib.Path(__file__).resolve().parents[1] / 'scripts/stage_gate.py'

MUTANTS = [
    ('skip_status', "if gate['status'] != 'PASS':", 'if False:'),
    ('skip_exit', "if type(gate['exit_code']) is not int or gate['exit_code'] != 0:", 'if False:'),
    ('skip_raw_present', 'if target.is_symlink() or not resolved.is_file():', 'if False:'),
    ('skip_raw_sha', 'or stream_sha(resolved) != stored:', 'or False:'),
    ('skip_digest', "if type(manifest['manifest_sha256']) is not str or digest(body) != manifest['manifest_sha256']:", 'if False:'),
    ('skip_self_signed', 'elif implementer == verifier:', 'elif False:'),
    ('skip_scope_escalation', "if claim['scope'] == 'production' and scope == 'isolated':", 'if False:'),
    ('skip_wording', 'if word in lowered:', 'if False:'),
    ('skip_gate_missing', 'for gid in sorted(set(required) - set(levels)):', 'for gid in []:'),
    ('skip_production_binding', "if evidence['release_gate_state'] != 'PASS':", 'if False:'),
]

KINDS = {
    'skip_status': 'status',
    'skip_exit': 'exit',
    'skip_raw_present': 'missing',
    'skip_raw_sha': 'tamper',
    'skip_digest': 'digest',
    'skip_self_signed': 'self',
    'skip_scope_escalation': 'scope',
    'skip_wording': 'wording',
    'skip_gate_missing': 'required',
    'skip_production_binding': 'production',
}

EXPECTED = {
    'skip_status': 'gate_not_run',
    'skip_exit': 'gate_exit',
    'skip_raw_present': 'gate_raw_missing',
    'skip_raw_sha': 'gate_raw_sha',
    'skip_digest': 'manifest_digest',
    'skip_self_signed': 'review_self_signed',
    'skip_scope_escalation': 'claim_scope_escalation',
    'skip_wording': 'claim_production_wording',
    'skip_gate_missing': 'gate_missing',
    'skip_production_binding': 'production_unbound',
}


def apply(kind, module, root):
    log = root / 'logs/spec.txt'
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('ok' + chr(10), encoding='utf-8')
    body = {
        'schema': 'stage-manifest/2',
        'stage_id': 'stage-0.1',
        'candidate_sha': 'a' * 40,
        'base_sha': 'b' * 40,
        'scope': 'isolated',
        'required_min_level': 'I2',
        'required_gate_ids': ['spec'],
        'gates': [{'id': 'spec', 'command': 'python scripts/check_all.py', 'exit_code': 0,
                   'raw_log': 'logs/spec.txt',
                   'raw_log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
                   'independence': 'I2', 'status': 'PASS'}],
        'claims': [{'id': 'spec-tools', 'statement': 'specification tools pass', 'level': 'I2',
                    'scope': 'isolated', 'gate_ids': ['spec']}],
        'not_claimed': ['production', 'm6-migration'],
        'reviewed_by': {'implementer_id': 'impl', 'reviewer_id': 'ver', 'role': 'independent-verifier',
                        'independent': True, 'session': 's', 'window_start': '2026-01-01T00:00:00Z',
                        'window_end': '2026-01-01T01:00:00Z'},
    }
    if kind == 'status':
        body['gates'][0]['status'] = 'NOT_RUN'
    elif kind == 'exit':
        body['gates'][0]['exit_code'] = 3
    elif kind == 'missing':
        log.unlink()
    elif kind == 'tamper':
        log.write_text('tampered' + chr(10), encoding='utf-8')
    elif kind == 'digest':
        body['required_min_level'] = 'I0'
    elif kind == 'self':
        body['reviewed_by']['reviewer_id'] = 'impl'
    elif kind == 'scope':
        body['claims'][0]['scope'] = 'production'
    elif kind == 'wording':
        body['claims'][0]['statement'] = 'production ready'
    elif kind == 'required':
        body['required_gate_ids'] = ['spec', 'absent']
    elif kind == 'production':
        body['scope'] = 'production'
        body['production_evidence'] = {'acceptance_status_sha256': 'c' * 64,
                                       'release_gate_state': 'BLOCK',
                                       'release_gate_sha256': 'd' * 64}
    else:
        raise AssertionError('unknown kind')
    return module.build_manifest(body)


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
                    manifest = apply(KINDS[name], module, work)
                    try:
                        reported = [c for c, _d in module.validate(manifest, work)]
                    except Exception as error:
                        reported = ['exception:' + type(error).__name__]
                    self.assertNotIn(EXPECTED[name], reported, 'mutant survived: ' + name)


if __name__ == '__main__':
    unittest.main()