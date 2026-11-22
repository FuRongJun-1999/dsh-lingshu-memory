"""Mutation killers for the stage evidence manifest gate (stage-0.1)."""
import hashlib
import importlib.util
import pathlib
import tempfile
import unittest

GATE = pathlib.Path(__file__).resolve().parents[1] / 'scripts/stage_gate.py'

MUTANTS = [
    ('skip_status_check', "if gate['status'] != 'PASS':", 'if False:'),
    ('skip_exit_check', "if type(gate['exit_code']) is not int or gate['exit_code'] != 0:", 'if False:'),
    ('skip_raw_missing', 'if not path.is_file():', 'if False:'),
    ('skip_raw_sha', "if HEX64.fullmatch(gate['raw_log_sha256'] or '') is None or _sha(path) != gate['raw_log_sha256']:", 'if False:'),
    ('allow_self_signed', "if reviewer['implementer'] is not False:", 'if False:'),
    ('skip_scope_escalation', "if claim['scope'] == 'production' and scope == 'isolated':", 'if False:'),
    ('skip_production_wording', 'if word in low:', 'if False:'),
]


def build(root):
    log = root / 'logs/spec.txt'
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('ok' + chr(10), encoding='utf-8')
    return {
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


VIOLATIONS = {
    'skip_status_check': ('gate_not_run', 'status'),
    'skip_exit_check': ('gate_exit', 'exit'),
    'skip_raw_missing': ('gate_raw_missing', 'missing'),
    'skip_raw_sha': ('gate_raw_sha', 'tamper'),
    'allow_self_signed': ('review_self_signed', 'self'),
    'skip_scope_escalation': ('claim_scope_escalation', 'scope'),
    'skip_production_wording': ('claim_production_wording', 'wording'),
}


def apply(kind, manifest, root):
    if kind == 'status':
        manifest['required_gates'][0]['status'] = 'NOT_RUN'
    elif kind == 'exit':
        manifest['required_gates'][0]['exit_code'] = 2
    elif kind == 'missing':
        (root / 'logs/spec.txt').unlink()
    elif kind == 'tamper':
        (root / 'logs/spec.txt').write_text('tampered' + chr(10), encoding='utf-8')
    elif kind == 'self':
        manifest['reviewed_by']['implementer'] = True
    elif kind == 'scope':
        manifest['claims'][0]['scope'] = 'production'
    elif kind == 'wording':
        manifest['claims'][0]['statement'] = 'production ready'
    else:
        raise AssertionError('unknown violation kind')


class StageGateMutationTests(unittest.TestCase):
    def test_every_gate_check_is_load_bearing(self):
        original = GATE.read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as tmp:
            for name, old, new in MUTANTS:
                with self.subTest(name=name):
                    self.assertIn(old, original, 'anchor missing: ' + name)
                    work = pathlib.Path(tmp) / name
                    work.mkdir()
                    mutant_path = work / 'stage_gate.py'
                    mutant_path.write_text(original.replace(old, new, 1), encoding='utf-8')
                    spec = importlib.util.spec_from_file_location('_gate_mut', mutant_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    code, kind = VIOLATIONS[name]
                    manifest = build(work)
                    apply(kind, manifest, work)
                    try:
                        reported = [c for c, _d in module.validate(manifest, work)]
                    except Exception as error:
                        reported = ['exception:' + type(error).__name__]
                    self.assertNotIn(code, reported, 'mutant survived: ' + name)


if __name__ == '__main__':
    unittest.main()