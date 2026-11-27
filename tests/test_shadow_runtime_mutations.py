"""Mutation killers for MD+JSON shadow_runtime durability, recovery, and audit invariants."""
import importlib.util
import io
import pathlib
import tempfile
import unittest
from framework.spec import ROOT
from shadow_runtime import audit as audit_mod
from shadow_runtime import store as store_mod


class ShadowRuntimeMutationTests(unittest.TestCase):
    def test_audit_mutants_killed(self):
        mutants_a = [
            ("ignore_truncated_nl", "if is_last and not has_trailing_nl:", "if False:"),
            ("payload_leak_after_key_check", 'if "body" in obj or "content" in obj:', 'if False:'),
            ("allow_bool_seq", 'if type(obj["seq"]) is not int or obj["seq"] < 1:', 'if not isinstance(obj["seq"], int) or obj["seq"] < 1:'),
            ("skip_middle_utf8_guard", "except UnicodeDecodeError:", "except LookupError:"),
        ]
        orig_a = pathlib.Path(audit_mod.__file__).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            for idx, (name, old, new) in enumerate(mutants_a):
                with self.subTest(name=name):
                    self.assertIn(old, orig_a, "audit anchor missing: " + name)
                    pa = pathlib.Path(tmp) / ("a_mut_%d.py" % idx)
                    pa.write_text(orig_a.replace(old, new, 1), encoding="utf-8")
                    sa = importlib.util.spec_from_file_location("_a_mut", pa)
                    ma = importlib.util.module_from_spec(sa)
                    sa.loader.exec_module(ma)
                    ts = importlib.util.spec_from_file_location("_sh_tests_a", ROOT / "tests/test_shadow_runtime.py")
                    tm = importlib.util.module_from_spec(ts)
                    ts.loader.exec_module(tm)
                    tm.inspect_audit = ma.inspect_audit
                    res_a = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(tm.ShadowRuntimeR01ToR09Tests))
                    self.assertFalse(res_a.wasSuccessful(), "audit mutant survived: " + name)

    def test_store_mutants_killed(self):
        mutants = [
            ("allow_power_without_probe", 'if not probe.get("supported"):', "if False:"),
            ("empty_disk_absent", 'if tok_rec is None:\n            return {"commit_status": "unknown", "audit_state": audit_state, "integrity_failure": audit_info["state"] in ("degraded", "integrity_failure")}', 'if tok_rec is None:\n            return {"commit_status": "absent", "audit_state": audit_state, "integrity_failure": False}'),
            ("allow_overwrite_revision_md", "if md_target.exists() or meta_target.exists():", "if False:"),
            ("allow_overwrite_correct_revision_md", 'if self._md_path(node_id, new_rev).exists() or self._meta_path(node_id, new_rev).exists():', "if False:"),
            ("ignore_corrupt_index", 'postings=None if idx is None else idx["inverted"]', 'postings={} if idx is None else idx["inverted"]'),
            ("skip_cancel_fence_on_write", 'if action == "return_original_cancel":', "if False:"),
            ("skip_proof_sha_check", 'if _sha_obj(body) != proof["proof_sha"]:', "if False:"),
            ("skip_meta_sha_check", 'if type(meta["meta_sha"]) is not str or _sha_obj(body) != meta["meta_sha"]:', "if False:"),
            ("skip_manifest_state_binding", 'or meta["state"] != entry["state"]):', 'or False):'),
            ("selfcheck_fake_c_pass", '"status": "NOT_RUN"} for cid in req["check_ids"]', '"status": "PASS"} for cid in req["check_ids"]'),
            ("skip_transaction_recovery", '        with self._lock():\n            self._recover_pending_transactions()\n            return self.recover_token_state_unlocked(', '        with self._lock():\n            pass\n            return self.recover_token_state_unlocked('),
            ("skip_p1_index_rebuild", '        self._rebuild_index_locked(manifest, durable=intent["durable"], fault_hook=fault_hook)', '        pass'),
        ]
        orig_s = pathlib.Path(store_mod.__file__).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            for idx, (name, old, new) in enumerate(mutants):
                with self.subTest(name=name):
                    self.assertIn(old, orig_s, "anchor missing: " + name)
                    ps = pathlib.Path(tmp) / ("s_mut_%d.py" % idx)
                    ps.write_text(orig_s.replace(old, new, 1), encoding="utf-8")
                    ss = importlib.util.spec_from_file_location("_s_mut", ps)
                    ms = importlib.util.module_from_spec(ss)
                    ss.loader.exec_module(ms)
                    ts2 = importlib.util.spec_from_file_location("_sh_tests_s", ROOT / "tests/test_shadow_runtime.py")
                    tm2 = importlib.util.module_from_spec(ts2)
                    ts2.loader.exec_module(tm2)
                    tm2.ShadowMarkdownStore = ms.ShadowMarkdownStore
                    tm2.InjectedCrash = ms.InjectedCrash
                    method_name = "test_write_manifest_index_crash_recovery" if name in ("skip_transaction_recovery", "skip_p1_index_rebuild") else None
                    suite = (unittest.defaultTestLoader.loadTestsFromName(method_name, tm2.ShadowRuntimeR01ToR09Tests)
                             if method_name else unittest.defaultTestLoader.loadTestsFromTestCase(tm2.ShadowRuntimeR01ToR09Tests))
                    res_s = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
                    failed_names = {case._testMethodName for case, _ in res_s.failures + res_s.errors}
                    if name == "selfcheck_fake_c_pass":
                        self.assertIn("test_selfcheck_never_reports_unimplemented_checks_as_pass", failed_names)
                    self.assertFalse(res_s.wasSuccessful(), "mutant survived: " + name)


if __name__ == "__main__":
    unittest.main()
