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

    def test_frozen_source_anchor(self):
        graph=json.loads((ROOT/'spec/capability_graph.json').read_text(encoding='utf-8'))
        for mutation in ({'commit':'0'*40},{'path':'md_cg/unknown.py'},{'lines':[1,1000000]},{'lines':[True,2]}):
            with self.subTest(mutation=mutation):
                bad=copy.deepcopy(graph)
                bad['capabilities'][0]['upstream'].update(mutation)
                with self.assertRaisesRegex(ValueError,'上游锚'):
                    verify(bad)

    def test_exclusive_implementation_500_vs_501(self):
        graph=json.loads((ROOT/'spec/capability_graph.json').read_text(encoding='utf-8'))
        row=copy.deepcopy(graph['capabilities'][0])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'port.py'
            row.update(entry=dict(path='port.py',symbol='read_get'),dependencies=[],evidence=['port.py'],
                       implementation=[dict(path='port.py',symbol=None)])
            doc=dict(version=1,capabilities=[row])
            good='def read_get():'+chr(10)+'    pass'+chr(10)+('# 专属实现'+chr(10))*498
            path.write_text(good,encoding='utf-8')
            self.assertEqual(verify(doc,root)['read.get'],500)
            path.write_text(good+'# 超额'+chr(10),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'超过 500'):
                verify(doc,root)
