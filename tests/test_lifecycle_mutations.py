"""Mutation killers for LifecycleSandbox, EpochDecisionCache, and private BM25."""
import importlib.util
import io
import pathlib
import sys
import tempfile
import unittest
from framework import model as model_mod
from framework.spec import ROOT
from sandbox_runtime import lifecycle as lc_mod
from sandbox_runtime import retrieval as ret_mod


class LifecycleMutationTests(unittest.TestCase):
    def test_epoch_cache_and_bm25_mutants_killed(self):
        orig_m = pathlib.Path(model_mod.__file__).read_text(encoding="utf-8")
        old_m = "return self._entries.get((graph_epoch, tenant, node_id, revision, content_sha))"
        new_m = "return self._entries.get((0, tenant, node_id, revision, content_sha))"
        self.assertIn(old_m, orig_m)
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "m_mut.py"
            p.write_text(orig_m.replace(old_m, new_m, 1), encoding="utf-8")
            mname = "framework._m_mut"
            ms = importlib.util.spec_from_file_location(mname, p)
            mm = importlib.util.module_from_spec(ms)
            sys.modules[mname] = mm
            ms.loader.exec_module(mm)
            ts = importlib.util.spec_from_file_location("_lc_tests_m", ROOT / "tests/test_lifecycle.py")
            tm = importlib.util.module_from_spec(ts)
            ts.loader.exec_module(tm)
            tm.can_read_with_epoch_cache = mm.can_read_with_epoch_cache
            res_m = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(tm.EpochCacheTests))
            sys.modules.pop(mname, None)
            self.assertFalse(res_m.wasSuccessful(), "epoch cache mutant survived")

            orig_r = pathlib.Path(ret_mod.__file__).read_text(encoding="utf-8")
            old_r = "visible = [key for key in ids if self._store._allowed(key, ctx)]"
            new_r = "visible = list(self._store._records.keys())"
            self.assertIn(old_r, orig_r)
            pr = pathlib.Path(tmp) / "r_mut.py"
            pr.write_text(orig_r.replace(old_r, new_r, 1), encoding="utf-8")
            rs = importlib.util.spec_from_file_location("_r_mut", pr)
            rm = importlib.util.module_from_spec(rs)
            rs.loader.exec_module(rm)
            ts2 = importlib.util.spec_from_file_location("_lc_tests_r", ROOT / "tests/test_lifecycle.py")
            tm2 = importlib.util.module_from_spec(ts2)
            ts2.loader.exec_module(tm2)
            tm2.PrivateBM25Store = rm.PrivateBM25Store
            res_r = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(tm2.PrivateBM25Tests))
            self.assertFalse(res_r.wasSuccessful(), "bm25 hidden_doc leakage mutant survived")

    def test_lifecycle_mutants_killed(self):
        mutants = [
            ("skip_restore_verification", 'proof_fresh = self.is_verified(node_id, required_scope="restore") if action == "restore" else True', "proof_fresh = True"),
            ("allow_read_scope_for_restore", 'scope_covers = scope in ("full", "restore")', "scope_covers = bool(scope)"),
            ("allow_cancelled_write", 'if action == "return_original_cancel":', "if False:"),
            ("skip_cancel_epoch_fence", 'if req["fencing_epoch"] < sealed_epoch:', "if False:"),
            ("ignore_mixed_defer", "if saw_defer:", "if saw_defer and not matched_ids:"),
            ("allow_power_without_evidence", 'if req["durability_request"] == "power":', "if False:"),
            ("skip_correct_revision_edges", "if not edges_ok:", "if False:"),
            ("skip_modify_cas", 'if cur["revision"] != req["expected_revision"]:', "if False:"),
            ("skip_token_conflict", 'if action == "conflict":', "if False:"),
            ("skip_toctou_emit_check", "if not emit_allowed(prepared_binding, live_binding, live_now, True, reauth_ok, True):", "if False:"),
            ("skip_policy_bump_eviction", "def _bump_policy(self):\n        self.policy_generation += 1\n        self.graph_epoch += 1", "def _bump_policy(self):\n        self.policy_generation += 1"),
        ]
        orig = pathlib.Path(lc_mod.__file__).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            for idx, (name, old, new) in enumerate(mutants):
                with self.subTest(name=name):
                    self.assertIn(old, orig, "anchor missing: " + name)
                    p = pathlib.Path(tmp) / ("lc_mut_%d.py" % idx)
                    p.write_text(orig.replace(old, new, 1), encoding="utf-8")
                    spec = importlib.util.spec_from_file_location("_lc_mut", p)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    ts = importlib.util.spec_from_file_location("_lc_tests2", ROOT / "tests/test_lifecycle.py")
                    tm = importlib.util.module_from_spec(ts)
                    ts.loader.exec_module(tm)
                    tm.LifecycleSandbox = mod.LifecycleSandbox
                    res = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(tm))
                    self.assertFalse(res.wasSuccessful(), "mutant survived: " + name)


if __name__ == "__main__":
    unittest.main()
