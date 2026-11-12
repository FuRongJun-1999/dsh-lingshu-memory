import json
import unittest
from framework.spec import ROOT

class ContextContractTests(unittest.TestCase):
 def test_scope_and_runtime_boundary(self):
    d=json.loads((ROOT/"spec/context_loop.json").read_text(encoding="utf-8"))
    self.assertFalse(d["scope"]["production_fallback"])
    self.assertEqual(d["scope"]["environment"],"isolated_synthetic")
    self.assertEqual(d["runtime_acceptance"],"NOT_RUN")
    self.assertEqual(d["llm_evaluation"],"NOT_RUN")
 def test_false_positive_cases_planned(self):
    d=json.loads((ROOT/"spec/context_loop.json").read_text(encoding="utf-8"))
    self.assertTrue({"query_result_claim_binding","independent_effect_probe","no_default_production"}<=set(d["obligations"]))
    self.assertTrue({"irrelevant_dummy_search","production_fallback","side_effect_without_log","large_irrelevant_corpus"}<=set(d["negative_cases"]))
