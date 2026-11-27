import copy
import json
import unittest
from framework.migration import load_inventory
from scripts.memory_migration_status import ROOT, verify, render


class MigrationStatusTests(unittest.TestCase):
    def setUp(self):
        def read(name):
            return json.loads((ROOT/'spec'/name).read_text(encoding='utf-8'))
        self.doc=read('memory_migration_status.json')
        self.inventory=load_inventory()
        self.graph=read('capability_graph.json')

    def test_44_operations_and_boundaries(self):
        stats=verify(self.doc,self.inventory,self.graph)
        self.assertEqual(stats,{'partial':38,'not_migrated':6})
        self.assertEqual(render(self.doc,stats),(ROOT/'docs/MEMORY_MIGRATION_STATUS.md').read_text(encoding='utf-8'))

    def test_dropped_operations_and_promoted_legacy_calls_are_rejected(self):
        for mutation in ('drop','grant','guess','unverified'):
            with self.subTest(mutation=mutation):
                doc,graph=copy.deepcopy(self.doc),copy.deepcopy(self.graph)
                rows=doc['operations']; read=next(x for x in rows if (x['tool'],x['op'])==('cg','read'))
                if mutation=='drop': rows.pop()
                if mutation=='grant': read['runtime_ready']=True
                if mutation=='guess': read['evidence'][0]['capability']='write.token'
                if mutation=='unverified': next(x for x in graph['capabilities'] if x['id']=='read.get')['state']='planned'
                with self.assertRaises(ValueError): verify(doc,self.inventory,graph)
