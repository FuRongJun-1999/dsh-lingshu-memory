import copy
import json
import tempfile
import unittest
from pathlib import Path
from scripts.capability_graph import ROOT, verify


class CapabilityBudgetTests(unittest.TestCase):
    def test_missing_shared_inventory_is_rejected(self):
        graph=json.loads((ROOT/'spec/capability_graph.json').read_text(encoding='utf-8'))
        report=verify(graph)
        self.assertIn('transaction.storage', report)
        example=copy.deepcopy(graph)
        del next(n for n in example['capabilities'] if n['id']=='transaction.storage')['implementation']
        with self.assertRaisesRegex(ValueError,'共享实现未登记'):
            verify(example)

    def test_over_budget_shared_module_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'shared.py').write_text('pass'+chr(10)*501,encoding='utf-8')
            graph=dict(version=1,capabilities=[dict(id='shared',state='dependency',dependencies=[],
                                                    implementation=[dict(path='shared.py',symbol=None)])])
            with self.assertRaisesRegex(ValueError,'共享实现超过 500'):
                verify(graph, root)
