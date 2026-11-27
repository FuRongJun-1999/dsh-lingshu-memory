import inspect
import unittest

from framework import capability_help as help_module
from framework.spec import ROOT, digest, parse


class CapabilityHelpTests(unittest.TestCase):
    def setUp(self):
        self.graph=parse((ROOT/'spec/capability_graph.json').read_text(encoding='utf-8'))
        self.sha=digest(self.graph)

    def test_exact_public_conditions_and_no_execution_surface(self):
        report=help_module.capability_help(self.graph,expected_sha=self.sha,capability='read.get')
        self.assertEqual(set(report),{'scope','runtime_ready','items'})
        self.assertFalse(report['runtime_ready'])
        card,=report['items']; source=next(x for x in self.graph['capabilities'] if x['id']=='read.get')
        self.assertEqual(card,{k:source[k] for k in ('id','name','state','conditions','subfunctions','execution','negative','dependencies')})
        card['conditions'].clear()
        self.assertTrue(source['conditions'])

    def test_bounded_list_excludes_dependencies_and_unknowns(self):
        first=help_module.capability_help(self.graph,expected_sha=self.sha,limit=2)
        expected=sorted(x['id'] for x in self.graph['capabilities'] if x['state']=='isolated')[:2]
        self.assertEqual([x['id'] for x in first['items']],expected)
        for key in ('policy.read','missing.capability'):
            self.assertEqual(help_module.capability_help(self.graph,expected_sha=self.sha,capability=key),{'error':'CAPABILITY_NOT_FOUND'})
        for lim in (0,65,True):
            with self.assertRaisesRegex(ValueError,'INVALID_HELP_LIMIT'):
                help_module.capability_help(self.graph,expected_sha=self.sha,limit=lim)

    def test_digest_mutation_detects_drift_even_when_ids_unchanged(self):
        target=next(x for x in self.graph['capabilities'] if x['id']=='read.get');target['conditions']=['drift fixture']
        req=dict(expected_sha=self.sha,capability='read.get')
        self.assertEqual(help_module.capability_help(self.graph,**req),{'error':'CATALOG_CHANGED'})
        src=inspect.getsource(help_module); guard=' or digest(graph) != expected_sha'
        self.assertEqual(src.count(guard),1)
        mutant={};exec(compile(src.replace(guard,'',1),'<help-digest-mutant>','exec'),mutant)
        self.assertEqual(mutant['capability_help'](self.graph,**req)['items'][0]['conditions'],['drift fixture'])
