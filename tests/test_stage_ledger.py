"""The stage ledger is machine-checked, and every failure branch is covered."""
import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HEAD = 'a' * 40


def load():
    path = ROOT / 'scripts' / 'ledger_check.py'
    spec = importlib.util.spec_from_file_location('_ledger_check', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def module_commands():
    spec = importlib.util.spec_from_file_location('_check_all', ROOT / 'scripts' / 'check_all.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.COMMANDS

def row(stage='stage-0.9-v1', commit=HEAD, tests=10, grade='I1', gates='NOT_RUN/BLOCK', note='ok'):
    return '| ' + stage + ' | ' + commit + ' | ' + str(tests) + ' | ' + grade + ' | ' + gates + ' | ' + note + ' |'


def document(*lines, boundary=None, risks='共因风险说明'):
    parts = list(lines)
    parts.append('## 当前边界声明')
    parts.append(boundary if boundary is not None else '至多记 I1；达到 I2 / I3 / I4 的条件另述。')
    parts.append('## 已知共因风险')
    parts.append(risks)
    return chr(10).join(parts)


def check(text, exists=True, ancestor=True, head=HEAD, wired=True, artifact=True, lag=0, checker=True):
    module = load()
    root = module.ROOT
    chain = module.ROOT / 'scripts' / 'check_all.py'
    real_read = pathlib.Path.read_text
    if not wired:
        module.Path.read_text = lambda self, encoding=None: 'no ledger here' if self == chain else real_read(self, encoding=encoding)
    try:
        return module.check_text(text, root,
                                exists=lambda commit: exists,
                                ancestor=lambda older, newer: ancestor,
                                head=head,
                                artifact=lambda commit: artifact,
                                lag=lambda commit: lag,
                                checker=lambda commit: checker)
    finally:
        module.Path.read_text = real_read


def full_document(**overrides):
    rows = [row('stage-0.1-v%d' % index, '{:040x}'.format(index + 1), tests=100 + index) for index in range(12)]
    return document(*rows, **overrides)


class LedgerBranchTests(unittest.TestCase):
    def test_clean_document_passes(self):
        self.assertEqual(check(full_document()), [])

    def test_empty_ledger_is_flagged(self):
        self.assertIn('ledger_empty', check(document()))

    def test_too_few_rows_is_flagged(self):
        self.assertIn('too_few_rows', check(document(row(tests=1))))

    def test_duplicate_commit_is_flagged(self):
        rows = [row('stage-0.1-v%d' % index, HEAD, tests=100 + index) for index in range(10)]
        self.assertIn('duplicate_commit:stage-0.1-v1', check(document(*rows)))

    def test_duplicate_stage_is_flagged(self):
        rows = [row('stage-0.1-v1', '{:040x}'.format(index + 1), tests=100 + index) for index in range(10)]
        self.assertIn('duplicate_stage:stage-0.1-v1', check(document(*rows)))

    def test_bad_gates_value_is_flagged(self):
        rows = [row('stage-0.1-v%d' % index, '{:040x}'.format(index + 1), tests=100 + index) for index in range(10)]
        rows[0] = row('stage-0.1-v0', '{:040x}'.format(1), tests=100, gates='PASS/BLOCK')
        self.assertIn('bad_gates:stage-0.1-v0', check(document(*rows)))

    def test_grade_above_ceiling_is_flagged(self):
        rows = [row('stage-0.1-v%d' % index, '{:040x}'.format(index + 1)) for index in range(8)]
        rows[3] = row('stage-0.1-v3', '{:040x}'.format(4), tests=103, grade='I2')
        self.assertIn('grade_ceiling:stage-0.1-v3', check(document(*rows)))

    def test_overclaim_is_flagged_for_fullwidth_and_zero_width(self):
        for note in ('生产　通过', '生产\u200b通过', 'PRODUCTION　PASS', '可 上 线'):
            rows = [row('stage-0.1-v%d' % index, '{:040x}'.format(index + 1)) for index in range(8)]
            rows[7] = row('stage-0.1-v7', '{:040x}'.format(8), tests=107, note=note)
            self.assertIn('overclaim:stage-0.1-v7', check(document(*rows)), note)

    def test_missing_anchor_doc_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'docs').mkdir()
            (root / 'scripts').mkdir()
            (root / 'scripts' / 'check_all.py').write_text('ledger_check.py' + chr(10), encoding='utf-8')
            text = full_document()
            problems = load().check_text(text, root, exists=lambda c: True,
                                          ancestor=lambda a, b: True, head=HEAD,
                                          artifact=lambda c: True, lag=lambda c: 0, checker=lambda c: True)
            self.assertIn('missing_anchor_doc', problems)

    def test_anchor_doc_sections_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'docs').mkdir()
            (root / 'scripts').mkdir()
            (root / 'scripts' / 'check_all.py').write_text('ledger_check.py' + chr(10), encoding='utf-8')
            (root / 'docs' / 'EXTERNAL_ANCHORS.md').write_text('# 外部锚' + chr(10) + '## I2' + chr(10), encoding='utf-8')
            problems = load().check_text(full_document(), root, exists=lambda c: True,
                                          ancestor=lambda a, b: True, head=HEAD,
                                          artifact=lambda c: True, lag=lambda c: 0)
            self.assertIn('anchor_section_missing:I3', problems)
            self.assertIn('anchor_missing_forbidden', problems)

    def test_real_anchor_doc_passes(self):
        module = load()
        self.assertEqual(module.check_text(module.LEDGER.read_text(encoding='utf-8'), module.ROOT), [])
    def test_malformed_table_row_is_flagged(self):
        text = full_document() + chr(10) + '| stage-0.1-v99 | not-a-commit | 1 |' + chr(10)
        codes = check(text)
        self.assertTrue(any(code.startswith('ledger_row_malformed') for code in codes), codes)

    def test_negation_window_does_not_exempt_the_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'docs').mkdir()
            line = '这不是没问题：本版本 production ready，可以放心上线。'
            (root / 'docs' / 'TRICK.md').write_text(line + chr(10), encoding='utf-8')
            self.assertTrue(any(code.startswith('doc_overclaim') for code in load().scan_docs(root)))

    def test_checker_self_artifact_is_required(self):
        self.assertTrue(load().artifact_present(load().ROOT, 'HEAD', 'scripts/ledger_check.py'))

    def test_wiring_uses_module_level_commands(self):
        import importlib
        spec = importlib.util.spec_from_file_location('_check_all', ROOT / 'scripts' / 'check_all.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        flat = [' '.join(entry) for entry in module.COMMANDS]
        self.assertTrue(any('ledger_check.py' in entry for entry in flat), flat)
    def test_homoglyph_claim_is_still_caught(self):
        self.assertIn('productionready', load().squash('pr' + chr(0x043e) + 'duction-ready'))

    def test_wiring_is_behavioural_not_substring(self):
        result = subprocess.run([sys.executable, '-B', 'scripts/ledger_check.py'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', errors='replace')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('STAGE LEDGER: PASS', result.stdout)

    def test_check_all_commands_execute_the_ledger(self):
        flat = [' '.join(entry) for entry in module_commands()]
        self.assertTrue(any(entry.endswith('scripts/ledger_check.py') for entry in flat), flat)
    def test_stale_ledger_is_flagged(self):
        codes = check(full_document(), lag=99)
        self.assertTrue(any(code.startswith('ledger_stale') for code in codes), codes)

    def test_fresh_ledger_is_accepted(self):
        self.assertNotIn('ledger_stale', check(full_document(), lag=3))
    def test_missing_artifact_is_flagged(self):
        self.assertIn('missing_artifact:stage-0.1-v0', check(full_document(), artifact=False))

    def test_non_positive_tests_is_flagged(self):
        rows = [row('stage-0.1-v%d' % index, '{:040x}'.format(index + 1), tests=100 + index) for index in range(10)]
        rows[0] = row('stage-0.1-v0', '{:040x}'.format(1), tests=0)
        self.assertIn('tests_not_positive:stage-0.1-v0', check(document(*rows)))

    def test_tests_must_not_decrease(self):
        rows = [row('stage-0.1-v%d' % index, '{:040x}'.format(index + 1), tests=100 + index) for index in range(10)]
        rows[5] = row('stage-0.1-v5', '{:040x}'.format(6), tests=1)
        self.assertIn('tests_not_monotonic:stage-0.1-v5', check(document(*rows)))
    def test_doc_overclaim_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'docs').mkdir()
            (root / 'docs' / 'CLAIM.md').write_text('本系统生产可用。' + chr(10), encoding='utf-8')
            problems = load().scan_docs(root)
            self.assertIn('doc_overclaim:CLAIM.md:1', problems)

    def test_negated_doc_claim_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'docs').mkdir()
            (root / 'docs' / 'BOUND.md').write_text('本轮不代表生产可用，也不授权上线。' + chr(10), encoding='utf-8')
            self.assertEqual(load().scan_docs(root), [])

    def test_dropped_forbidden_token_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'docs').mkdir()
            (root / 'docs' / 'WEAK.md').write_text('这不禁止说：生产放行。' + chr(10), encoding='utf-8')
            self.assertIn('dropped_token:WEAK.md', load().scan_docs(root))

    def test_real_docs_pass_the_scanner(self):
        self.assertEqual(load().scan_docs(load().ROOT), [])
    def test_unknown_commit_is_flagged(self):
        self.assertIn('unknown_commit:stage-0.1-v0', check(full_document(), exists=False))

    def test_row_order_violation_is_flagged(self):
        self.assertIn('row_order:stage-0.1-v1', check(full_document(), ancestor=False))

    def test_row_outside_head_history_is_flagged(self):
        rows = [row('stage-0.1-v%d' % index, '{:040x}'.format(index + 1), tests=100 + index) for index in range(10)]
        module = load()
        problems = module.check_text(document(*rows), module.ROOT,
                                     exists=lambda commit: True, ancestor=lambda older, newer: newer != HEAD,
                                     head=HEAD, artifact=lambda commit: True, checker=lambda commit: True)
        self.assertIn('row_not_in_history:stage-0.1-v9', problems)

    def test_missing_section_is_flagged(self):
        text = chr(10).join([row('stage-0.1-v%d' % index, '{:040x}'.format(index + 1), tests=100 + index) for index in range(10)])
        problems = check(text)
        self.assertIn('missing_section:## 当前边界声明', problems)

    def test_empty_boundary_is_flagged(self):
        self.assertIn('boundary_empty', check(full_document(boundary='')))

    def test_boundary_without_ceiling_is_flagged(self):
        self.assertIn('boundary_without_ceiling', check(full_document(boundary='本仓库尚未评级。')))

    def test_boundary_without_higher_grades_is_flagged(self):
        self.assertIn('boundary_missing:I2', check(full_document(boundary='至多记 I1。')))

    def test_unwired_check_all_is_flagged(self):
        self.assertIn('ledger_not_wired', check(full_document(), wired=False))


class LedgerFreezeTests(unittest.TestCase):
    def test_forbidden_oracle_is_not_weakened(self):
        module = load()
        frozen = {'productionpass', 'productionready', '生产通过', '生产就绪', '可上线', '生产可用'}
        self.assertLessEqual(frozen, set(module.FROZEN_FORBIDDEN))

    def test_ledger_path_is_pinned(self):
        module = load()
        self.assertEqual(module.LEDGER, module.ROOT / 'docs' / 'STAGE_LEDGER.md')

    def test_ceiling_constant_is_i1(self):
        self.assertEqual(load().MAX_GRADE, 'I1')

    def test_real_ledger_passes_the_checker(self):
        module = load()
        text = module.LEDGER.read_text(encoding='utf-8')
        self.assertEqual(module.check_text(text, module.ROOT), [])


class LedgerWiringTests(unittest.TestCase):
    def test_check_all_declares_the_ledger_gate(self):
        text = (ROOT / 'scripts' / 'check_all.py').read_text(encoding='utf-8')
        self.assertIn('ledger_check.py', text)

    def test_required_test_modules_exist(self):
        for name in ('test_stage_ledger.py', 'test_stage_gate.py', 'test_ed25519.py'):
            self.assertTrue((ROOT / 'tests' / name).is_file(), name)


if __name__ == '__main__':
    unittest.main()