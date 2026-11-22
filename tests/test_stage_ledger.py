"""The stage ledger is machine-checked, and every failure branch is covered."""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HEAD = 'a' * 40


def load():
    path = ROOT / 'scripts' / 'ledger_check.py'
    spec = importlib.util.spec_from_file_location('_ledger_check', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(stage='stage-0.9-v1', commit=HEAD, tests=10, grade='I1', gates='NOT_RUN/BLOCK', note='ok'):
    return '| ' + stage + ' | ' + commit + ' | ' + str(tests) + ' | ' + grade + ' | ' + gates + ' | ' + note + ' |'


def document(*lines, boundary=None, risks='共因风险说明'):
    parts = list(lines)
    parts.append('## 当前边界声明')
    parts.append(boundary if boundary is not None else '至多记 I1；达到 I2 / I3 / I4 的条件另述。')
    parts.append('## 已知共因风险')
    parts.append(risks)
    return chr(10).join(parts)


def check(text, exists=True, ancestor=True, head=HEAD, wired=True):
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
                                head=head)
    finally:
        module.Path.read_text = real_read


def full_document(**overrides):
    rows = [row('stage-0.1-v%d' % index, '{:040x}'.format(index + 1)) for index in range(8)]
    return document(*rows, **overrides)


class LedgerBranchTests(unittest.TestCase):
    def test_clean_document_passes(self):
        self.assertEqual(check(full_document()), [])

    def test_empty_ledger_is_flagged(self):
        self.assertIn('ledger_empty', check(document()))

    def test_too_few_rows_is_flagged(self):
        self.assertIn('too_few_rows', check(document(row())))

    def test_duplicate_commit_is_flagged(self):
        rows = [row('stage-0.1-v%d' % index, HEAD) for index in range(8)]
        self.assertIn('duplicate_commit:stage-0.1-v1', check(document(*rows)))

    def test_duplicate_stage_is_flagged(self):
        rows = [row('stage-0.1-v1', '{:040x}'.format(index + 1)) for index in range(8)]
        self.assertIn('duplicate_stage:stage-0.1-v1', check(document(*rows)))

    def test_bad_gates_value_is_flagged(self):
        rows = [row('stage-0.1-v%d' % index, '{:040x}'.format(index + 1)) for index in range(8)]
        rows[0] = row('stage-0.1-v0', '{:040x}'.format(1), gates='PASS/BLOCK')
        self.assertIn('bad_gates:stage-0.1-v0', check(document(*rows)))

    def test_grade_above_ceiling_is_flagged(self):
        rows = [row('stage-0.1-v%d' % index, '{:040x}'.format(index + 1)) for index in range(8)]
        rows[3] = row('stage-0.1-v3', '{:040x}'.format(4), grade='I2')
        self.assertIn('grade_ceiling:stage-0.1-v3', check(document(*rows)))

    def test_overclaim_is_flagged_for_fullwidth_and_zero_width(self):
        for note in ('生产　通过', '生产\u200b通过', 'PRODUCTION　PASS', '可 上 线'):
            rows = [row('stage-0.1-v%d' % index, '{:040x}'.format(index + 1)) for index in range(8)]
            rows[7] = row('stage-0.1-v7', '{:040x}'.format(8), note=note)
            self.assertIn('overclaim:stage-0.1-v7', check(document(*rows)), note)

    def test_unknown_commit_is_flagged(self):
        self.assertIn('unknown_commit:stage-0.1-v0', check(full_document(), exists=False))

    def test_row_order_violation_is_flagged(self):
        self.assertIn('row_order:stage-0.1-v1', check(full_document(), ancestor=False))

    def test_row_outside_head_history_is_flagged(self):
        rows = [row('stage-0.1-v%d' % index, '{:040x}'.format(index + 1)) for index in range(8)]
        module = load()
        problems = module.check_text(document(*rows), module.ROOT,
                                     exists=lambda commit: True, ancestor=lambda older, newer: newer != HEAD,
                                     head=HEAD)
        self.assertIn('row_not_in_history:stage-0.1-v7', problems)

    def test_missing_section_is_flagged(self):
        text = chr(10).join([row('stage-0.1-v%d' % index, '{:040x}'.format(index + 1)) for index in range(8)])
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
        frozen = {'productionpass', 'productionready', '生产通过', '生产就绪', '可上线', '生产放行'}
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