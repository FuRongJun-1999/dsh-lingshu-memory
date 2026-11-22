"""Independent expectations for the stage manifest gate (schema v2)."""
import copy
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from framework.spec import ROOT
import scripts.stage_gate as gate_mod

FIELDS_BASE = {
    'schema': 'stage-manifest/2',
    'stage_id': 'stage-0.1',
    'candidate_sha': 'a' * 40,
    'base_sha': 'b' * 40,
    'scope': 'isolated',
    'required_min_level': 'I2',
    'required_gate_ids': ['spec'],
    'not_claimed': ['production', 'm6-migration'],
    'reviewed_by': {
        'implementer_id': 'dsh-implementer',
        'reviewer_id': 'independent-verifier-1',
        'role': 'independent-verifier',
        'independent': True,
        'session': 'session-b',
        'window_start': '2026-11-22T15:00:00Z',
        'window_end': '2026-11-22T15:30:00Z',
    },
}


def make(root, mutate=None):
    log = root / 'logs/spec.txt'
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('ok' + chr(10), encoding='utf-8')
    body = copy.deepcopy(FIELDS_BASE)
    body['gates'] = [{'id': 'spec', 'command': 'python scripts/check_all.py', 'exit_code': 0,
                      'raw_log': 'logs/spec.txt',
                      'raw_log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
                      'independence': 'I2', 'status': 'PASS'}]
    body['claims'] = [{'id': 'spec-tools', 'statement': 'specification tools pass', 'level': 'I2',
                       'scope': 'isolated', 'gate_ids': ['spec']}]
    if mutate is not None:
        mutate(body, root)
    return gate_mod.build_manifest(body)


def codes(manifest, root):
    return [code for code, _detail in gate_mod.validate(manifest, root)]


class StageGateV2Tests(unittest.TestCase):
    def test_valid_isolated_manifest_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertEqual(codes(make(root), root), [])

    def test_manifest_digest_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = make(root)
            manifest['required_min_level'] = 'I0'
            self.assertIn('manifest_digest', codes(manifest, root))

    def test_production_scope_requires_external_evidence(self):
        def mutate(body, root):
            body['scope'] = 'production'
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = make(root, mutate)
            self.assertIn('production_unbound', codes(manifest, root))

    def test_production_scope_rejects_blocking_release_gate(self):
        def mutate(body, root):
            body['scope'] = 'production'
            body['production_evidence'] = {'acceptance_status_sha256': 'c' * 64,
                                           'release_gate_state': 'BLOCK',
                                           'release_gate_sha256': 'd' * 64}
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = make(root, mutate)
            self.assertIn('production_unbound', codes(manifest, root))

    def test_required_gate_ids_must_match_declared_gates(self):
        def mutate(body, root):
            body['required_gate_ids'] = ['spec', 'shadow']
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertIn('gate_missing', codes(make(root, mutate), root))

    def test_undeclared_gate_is_rejected(self):
        def mutate(body, root):
            body['gates'].append(dict(body['gates'][0], id='extra'))
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertIn('gate_extra', codes(make(root, mutate), root))

    def test_gate_below_minimum_level_is_rejected(self):
        def mutate(body, root):
            body['gates'][0]['independence'] = 'I1'
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertIn('gate_level_too_low', codes(make(root, mutate), root))

    def test_not_run_gate_blocks_promotion(self):
        def mutate(body, root):
            body['gates'][0]['status'] = 'NOT_RUN'
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertIn('gate_not_run', codes(make(root, mutate), root))

    def test_backslash_and_drive_paths_are_rejected(self):
        for raw in ('logs\\spec.txt', 'C:/logs/spec.txt'):
            with self.subTest(raw=raw):
                def mutate(body, root, raw=raw):
                    body['gates'][0]['raw_log'] = raw
                with tempfile.TemporaryDirectory() as tmp:
                    root = pathlib.Path(tmp)
                    self.assertIn('gate_raw_path', codes(make(root, mutate), root))

    def test_traversal_outside_root_is_rejected(self):
        def mutate(body, root):
            body['gates'][0]['raw_log'] = '../escape.txt'
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'root'
            root.mkdir()
            self.assertIn('gate_raw_path', codes(make(root, mutate), root))

    def test_status_file_cannot_be_evidence(self):
        def mutate(body, root):
            body['gates'][0]['raw_log'] = 'spec/acceptance_status.json'
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertIn('gate_readonly_status', codes(make(root, mutate), root))

    def test_self_signed_reviewer_id_is_rejected(self):
        def mutate(body, root):
            body['reviewed_by']['reviewer_id'] = body['reviewed_by']['implementer_id']
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertIn('review_self_signed', codes(make(root, mutate), root))

    def test_integer_one_cannot_impersonate_independence(self):
        def mutate(body, root):
            body['reviewed_by']['independent'] = 1
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertIn('review_not_independent', codes(make(root, mutate), root))

    def test_implementer_role_is_rejected(self):
        def mutate(body, root):
            body['reviewed_by']['role'] = 'implementer'
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertIn('review_role', codes(make(root, mutate), root))

    def test_review_window_must_be_ordered(self):
        def mutate(body, root):
            body['reviewed_by']['window_end'] = body['reviewed_by']['window_start']
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertIn('review_window', codes(make(root, mutate), root))

    def test_claim_below_minimum_level_is_rejected(self):
        def mutate(body, root):
            body['claims'][0]['level'] = 'I0'
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertIn('claim_level_too_low', codes(make(root, mutate), root))

    def test_duplicate_claim_ids_are_rejected(self):
        def mutate(body, root):
            body['claims'].append(dict(body['claims'][0]))
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertIn('claim_duplicate', codes(make(root, mutate), root))

    def test_isolated_scope_cannot_claim_production(self):
        def mutate(body, root):
            body['claims'][0]['scope'] = 'production'
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertIn('claim_scope_escalation', codes(make(root, mutate), root))

    def test_production_ready_wording_is_rejected(self):
        for phrase in ('ready for production', '生产就绪'):
            with self.subTest(phrase=phrase):
                def mutate(body, root, phrase=phrase):
                    body['claims'][0]['statement'] = phrase
                with tempfile.TemporaryDirectory() as tmp:
                    root = pathlib.Path(tmp)
                    self.assertIn('claim_production_wording', codes(make(root, mutate), root))

    def test_claim_gate_level_must_cover_claim(self):
        def mutate(body, root):
            body['claims'][0]['level'] = 'I3'
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertIn('claim_level_exceeds_gate', codes(make(root, mutate), root))

    def test_cli_distinguishes_fail_from_validator_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            good = make(root)
            path = root / 'manifest.json'
            path.write_text(json.dumps(good, sort_keys=True), encoding='utf-8')
            ok = subprocess.run([sys.executable, '-B', 'scripts/stage_gate.py', '--manifest', str(path)], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            path.write_text('{"schema": "stage-manifest/2", "schema": "stage-manifest/2"}', encoding='utf-8')
            dup = subprocess.run([sys.executable, '-B', 'scripts/stage_gate.py', '--manifest', str(path)], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(dup.returncode, 2, dup.stdout)
            good['gates'][0]['status'] = 'NOT_RUN'
            path.write_text(json.dumps(gate_mod.build_manifest({k: v for k, v in good.items() if k != 'manifest_sha256'}), sort_keys=True), encoding='utf-8')
            bad = subprocess.run([sys.executable, '-B', 'scripts/stage_gate.py', '--manifest', str(path)], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(bad.returncode, 1)
            self.assertIn('gate_not_run', bad.stdout)




def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace')


def commit(root, message):
    result = subprocess.run(['git', '-c', 'user.email=t@example.invalid', '-c', 'user.name=t',
                             'commit', '-q', '-m', message], cwd=root, capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)


def init_repo(root):
    git(root, 'init', '-q')
    notes = root / 'notes.txt'
    notes.write_text('n1' + chr(10), encoding='utf-8')
    git(root, 'add', '-A')
    commit(root, 'one')
    base = git(root, 'rev-parse', 'HEAD').stdout.strip()
    notes.write_text('n2' + chr(10), encoding='utf-8')
    git(root, 'add', '-A')
    commit(root, 'two')
    candidate = git(root, 'rev-parse', 'HEAD').stdout.strip()
    return base, candidate


class StageGateGitAnchorTests(unittest.TestCase):
    def test_tracked_evidence_at_candidate_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = make(root)
            base, candidate = init_repo(root)
            manifest['base_sha'] = base
            manifest['candidate_sha'] = candidate
            out = []
            gate_mod.git_check(manifest, root, out)
            self.assertEqual(out, [])

    def test_mutated_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = make(root)
            base, candidate = init_repo(root)
            extra = root / 'logs/spec.txt'
            extra.write_text('three' + chr(10), encoding='utf-8')
            manifest['base_sha'] = base
            manifest['candidate_sha'] = candidate
            out = []
            gate_mod.git_check(manifest, root, out)
            self.assertIn('gate_raw_untracked', [code for code, _d in out])

    def test_missing_candidate_commit_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = make(root)
            base, _candidate = init_repo(root)
            manifest['base_sha'] = base
            manifest['candidate_sha'] = 'f' * 40
            out = []
            gate_mod.git_check(manifest, root, out)
            self.assertIn('git_candidate_missing', [code for code, _d in out])

    def test_non_ancestor_base_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            base, candidate = init_repo(root)
            manifest = make(root)
            manifest['base_sha'] = candidate
            manifest['candidate_sha'] = base
            out = []
            gate_mod.git_check(manifest, root, out)
            self.assertIn('git_base_not_ancestor', [code for code, _d in out])

    def test_external_requirements_registry_is_authoritative(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = make(root)
            registry = root / 'requirements.json'
            registry.write_text(json.dumps(['spec', 'shadow']), encoding='utf-8')
            out = []
            gate_mod.requirements_check(manifest, registry, out)
            codes_out = [code for code, _d in out]
            self.assertIn('gate_missing', codes_out)
            registry.write_text(json.dumps(['spec']), encoding='utf-8')
            out = []
            gate_mod.requirements_check(manifest, registry, out)
            self.assertEqual(out, [])
            registry.write_text(json.dumps(['spec', 'other']), encoding='utf-8')
            out = []
            gate_mod.requirements_check(manifest, registry, out)
            codes_out = [code for code, _d in out]
            self.assertIn('gate_missing', codes_out)


if __name__ == '__main__':
    unittest.main()