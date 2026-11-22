"""The stage ledger is machine-checked, not prose."""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load():
    path = ROOT / 'scripts' / 'ledger_check.py'
    spec = importlib.util.spec_from_file_location('_ledger_check', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROW = '| stage-0.9-v1 | {commit} | 10 | {grade} | NOT_RUN/BLOCK | {note} |'
HEAD = '0' * 40


class LedgerTests(unittest.TestCase):
    def parse(self, text):
        return load().rows(text)

    def test_rows_are_parsed(self):
        text = ROW.format(commit=HEAD, grade='I1', note='ok')
        self.assertEqual(self.parse(text)[0]['independence'], 'I1')

    def test_prose_without_table_is_empty(self):
        self.assertEqual(self.parse('# title\nno rows here'), [])

    def test_malformed_row_is_ignored(self):
        text = '| stage-x | deadbeef | 10 | I1 | NOT_RUN/BLOCK | note |'
        self.assertEqual(self.parse(text), [])

    def test_ledger_file_declares_boundary_and_risk_sections(self):
        text = (ROOT / 'docs' / 'STAGE_LEDGER.md').read_text(encoding='utf-8')
        self.assertIn('## 当前边界声明', text)
        self.assertIn('## 已知共因风险', text)

    def test_ledger_rows_all_have_known_commits(self):
        module = load()
        text = (ROOT / 'docs' / 'STAGE_LEDGER.md').read_text(encoding='utf-8')
        for entry in module.rows(text):
            self.assertTrue(module.commit_exists(module.ROOT, entry['commit']), entry['stage'])

    def test_no_i1_row_claims_production_pass(self):
        module = load()
        text = (ROOT / 'docs' / 'STAGE_LEDGER.md').read_text(encoding='utf-8')
        for entry in module.rows(text):
            if entry['independence'] in ('I0', 'I1'):
                lowered = entry['note'].lower()
                for word in module.FORBIDDEN:
                    self.assertNotIn(word, lowered, entry['stage'])


if __name__ == '__main__':
    unittest.main()