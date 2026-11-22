"""Independent R01-R09 fault-injection and durability verification tests for MD+JSON shadow_runtime."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
from framework.spec import ROOT, canonical
from shadow_runtime.audit import inspect_audit
from shadow_runtime.durability import probe_platform_durability
from shadow_runtime.store import InjectedCrash, ShadowMarkdownStore

A = "2024-01-01T00:00:00Z"
B = "2024-01-10T00:00:00Z"
Q = "2024-01-05T00:00:00Z"


def ctx(principal="alice", tenant="t1", clearance=2, auth_epoch=1, policy_generation=1, expires_at=1000):
    return {
        "tenant": tenant, "principal": principal, "clearance": clearance,
        "auth_epoch": auth_epoch, "policy_generation": policy_generation, "expires_at": expires_at,
    }


def cspace():
    return {
        "carrier": {"state": "declared", "text": "md"},
        "method": {"state": "declared", "text": "exact"},
        "existence": {"state": "declared", "text": "present"},
        "attributes": [],
    }


def bitemp():
    return {
        "observed": {"start": {"state": "instant", "value": A}, "end": {"state": "instant", "value": B}},
        "effective": {"start": {"state": "instant", "value": A}, "end": {"state": "instant", "value": B}},
    }


def write_req(token, body, *, sensitivity=1, readers=("alice", "bob"), durability="process", kind="Write.create", node_id=None, expected_revision=None):
    r = {
        "kind": kind, "caller_token": token, "content": body, "declared_sensitivity": sensitivity,
        "reader_ceiling": sorted(set(readers)), "source_edges": [], "condition_space": cspace(),
        "bitemporal": bitemp(), "source_attribution": {"source_kind": "human", "source_id": "author-1"},
        "durability_request": durability,
    }
    if kind == "Write.modify":
        r["node_id"] = node_id
        r["expected_revision"] = expected_revision
    return r


class ShadowRuntimeR01ToR09Tests(unittest.TestCase):
    def test_r01_filter_before_limit_and_post_auth_tightening(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = ShadowMarkdownStore(tmp, synthetic=True)
            self.assertEqual(s.execute(write_req("t-bob", "alpha secret", readers=("bob",)), ctx("bob"), 10)["outcome"], "ok")
            self.assertEqual(s.execute(write_req("t-alice", "alpha public", readers=("alice", "bob")), ctx("alice"), 11)["outcome"], "ok")
            # Whitelist check: all disk files are plain text .md / .json / .jsonl / .lock (zero binary DB)
            allowed_ext = {".md", ".json", ".jsonl", ".lock"}
            for p in pathlib.Path(tmp).rglob("*"):
                if p.is_file():
                    self.assertIn(p.suffix, allowed_ext)
            res = s.execute({"kind": "Read.search", "query": "alpha", "limit": 1, "include_provenance": False, "condition_query": cspace(), "time_axis": "effective", "time_point": Q}, ctx("alice"), 12)
            self.assertEqual(res["outcome"], "ok")
            self.assertEqual(len(res["records"]), 1)
            self.assertEqual(res["records"][0]["body"], "alpha public")
            toctou = s.execute(
                {"kind": "Read.get", "node_id": "node-2", "include_provenance": False, "condition_query": cspace(), "time_axis": "effective", "time_point": Q},
                ctx("alice"), 13,
                current_context_provider=lambda: ctx("alice", clearance=0),
            )
            self.assertEqual(toctou["error_code"], "POLICY_CHANGED")

    def test_r02_crash_points_cross_process_race_and_cancel_fence(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 1. Inject crashes at every stage boundary before commit AND after response-lost boundary
            for stage in ("intent:before_replace", "token:before_replace", "md:before_replace", "meta:before_replace"):
                with self.subTest(stage=stage):
                    sub = pathlib.Path(tmp) / stage.replace(":", "_")
                    s = ShadowMarkdownStore(sub, synthetic=True)
                    def crash_hook(st, _p, target=stage):
                        if st == target:
                            raise InjectedCrash(st)
                    with self.assertRaises(InjectedCrash):
                        s.execute(write_req("tok-crash", "hello crash"), ctx("alice"), 10, fault_hook=crash_hook)
                    rec = s.recover_token_state(tenant="t1", principal="alice", operation="Write.create", caller_token="tok-crash")
                    self.assertEqual(rec["commit_status"], "unknown")

            # Crash between intent and token ledger: retry with different payload MUST reject as conflict, same payload -> unknown
            sub_int = pathlib.Path(tmp) / "intent_only_conflict"
            s_int = ShadowMarkdownStore(sub_int, synthetic=True)
            with self.assertRaises(InjectedCrash):
                s_int.execute(write_req("tok-ic", "first payload"), ctx("alice"), 10, fault_hook=lambda st, _p: (_ for _ in ()).throw(InjectedCrash(st)) if st == "token:before_replace" else None)
            self.assertEqual(s_int.execute(write_req("tok-ic", "different payload"), ctx("alice"), 11)["error_code"], "TOKEN_PAYLOAD_CONFLICT")
            self.assertEqual(s_int.execute(write_req("tok-ic", "first payload"), ctx("alice"), 12)["error_code"], "RECOVERY_UNCERTAIN")

            # Cancel cannot seal durable_cancel if platform durability probe fails, and cannot claim absent if intent+MD already exist
            sub_bad_cancel = pathlib.Path(tmp) / "bad_cancel_dur"
            s_bc = ShadowMarkdownStore(sub_bad_cancel, synthetic=True, durability_probe_fn=lambda _r: {"supported": False, "reason": "no_sync"})
            self.assertEqual(s_bc.execute({"kind": "Operation.cancel", "target_operation": "Write.create", "caller_token": "tc-bad", "fencing_epoch": 1, "reason": "abort"}, ctx("alice"), 10)["error_code"], "POWER_UNSUPPORTED")

            # 2. Cross-process OS lock race + response-lost idempotency
            mp_dir = pathlib.Path(tmp) / "mp_race"
            mp_dir.mkdir()
            worker_py = pathlib.Path(tmp) / "race_worker.py"
            worker_py.write_text(
                "import json, pathlib, sys\n"
                "sys.path.insert(0, sys.argv[1])\n"
                "from shadow_runtime.store import ShadowMarkdownStore\n"
                "s = ShadowMarkdownStore(sys.argv[2], synthetic=True, lock_timeout_s=5.0)\n"
                "req = {'kind':'Write.create','caller_token':'shared-tok','content':sys.argv[3],'declared_sensitivity':1,'reader_ceiling':['alice'],'source_edges':[],'condition_space':{'carrier':{'state':'declared','text':'md'},'method':{'state':'declared','text':'exact'},'existence':{'state':'declared','text':'present'},'attributes':[]},'bitemporal':{'observed':{'start':{'state':'instant','value':'2024-01-01T00:00:00Z'},'end':{'state':'instant','value':'2024-01-10T00:00:00Z'}},'effective':{'start':{'state':'instant','value':'2024-01-01T00:00:00Z'},'end':{'state':'instant','value':'2024-01-10T00:00:00Z'}}},'source_attribution':{'source_kind':'human','source_id':'author-1'},'durability_request':'process'}\n"
                "c = {'tenant':'t1','principal':'alice','clearance':2,'auth_epoch':1,'policy_generation':1,'expires_at':1000}\n"
                "r = s.execute(req, c, 10)\n"
                "pathlib.Path(sys.argv[4]).write_text(json.dumps({'outcome':r['outcome'],'code':r['error_code'],'node':r['historical_receipt']['node_id'] if r['historical_receipt'] else None}), encoding='utf-8')\n",
                encoding="utf-8",
            )
            out1 = pathlib.Path(tmp) / "w1.json"
            out2 = pathlib.Path(tmp) / "w2.json"
            env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
            p1 = subprocess.Popen([sys.executable, "-X", "utf8", "-B", str(worker_py), str(ROOT), str(mp_dir), "same body", str(out1)], env=env)
            p2 = subprocess.Popen([sys.executable, "-X", "utf8", "-B", str(worker_py), str(ROOT), str(mp_dir), "same body", str(out2)], env=env)
            self.assertEqual(p1.wait(timeout=20), 0)
            self.assertEqual(p2.wait(timeout=20), 0)
            r1 = json.loads(out1.read_text(encoding="utf-8"))
            r2 = json.loads(out2.read_text(encoding="utf-8"))
            self.assertEqual((r1["outcome"], r2["outcome"]), ("ok", "ok"))
            self.assertEqual(r1["node"], r2["node"])

            out3 = pathlib.Path(tmp) / "w3.json"
            p3 = subprocess.Popen([sys.executable, "-X", "utf8", "-B", str(worker_py), str(ROOT), str(mp_dir), "different body", str(out3)], env=env)
            self.assertEqual(p3.wait(timeout=20), 0)
            r3 = json.loads(out3.read_text(encoding="utf-8"))
            self.assertEqual(r3["code"], "TOKEN_PAYLOAD_CONFLICT")

            # 3. Cancel wins -> subsequent write blocked with CANCELLED
            s_cancel = ShadowMarkdownStore(pathlib.Path(tmp) / "cancel_win", synthetic=True)
            self.assertEqual(s_cancel.execute({"kind": "Operation.cancel", "target_operation": "Write.create", "caller_token": "tok-c", "fencing_epoch": 2, "reason": "abort"}, ctx("alice"), 10)["error_code"], "CANCELLED")
            self.assertEqual(s_cancel.execute(write_req("tok-c", "late body"), ctx("alice"), 11)["error_code"], "CANCELLED")
            rec_c = s_cancel.recover_token_state(tenant="t1", principal="alice", operation="Write.create", caller_token="tok-c")
            self.assertEqual(rec_c["commit_status"], "absent")
            self.assertEqual(rec_c["negative_basis"], "durable_cancel")

    def test_r03_process_arbitrary_subset_loss_and_empty_disk_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = ShadowMarkdownStore(tmp, synthetic=True)
            self.assertEqual(s.recover_token_state(tenant="t1", principal="alice", operation="Write.create", caller_token="never-seen")["commit_status"], "unknown")
            res = s.execute(write_req("tok-1", "persisted md body", durability="process"), ctx("alice"), 10)
            self.assertEqual(res["outcome"], "ok")
            md_file = next((pathlib.Path(tmp) / "nodes").rglob("rev_000001.md"))
            md_file.unlink()
            rec = s.recover_token_state(tenant="t1", principal="alice", operation="Write.create", caller_token="tok-1")
            self.assertEqual(rec["commit_status"], "unknown")
            md_file.write_text("tampered", encoding="utf-8")
            rec_tamper = s.recover_token_state(tenant="t1", principal="alice", operation="Write.create", caller_token="tok-1")
            self.assertEqual(rec_tamper["commit_status"], "unknown")
            self.assertTrue(rec_tamper["integrity_failure"])

    def test_r04_platform_power_durability_real_probe_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            real_probe = probe_platform_durability(pathlib.Path(tmp))
            self.assertTrue(real_probe["supported"], real_probe)
            s = ShadowMarkdownStore(tmp, synthetic=True)
            ok_power = s.execute(write_req("tok-pwr", "power verified md", durability="power"), ctx("alice"), 10)
            self.assertEqual(ok_power["outcome"], "ok")
            self.assertEqual(ok_power["historical_receipt"]["durability_actual"], "power")

            sub = pathlib.Path(tmp) / "no_dir_sync"
            def bad_probe(root_dir):
                return probe_platform_durability(root_dir, dir_sync_fn=lambda _d: (_ for _ in ()).throw(OSError("ENOTSUP")))
            s_bad = ShadowMarkdownStore(sub, synthetic=True, durability_probe_fn=bad_probe)
            denied_power = s_bad.execute(write_req("tok-pwr-fail", "must fail", durability="power"), ctx("alice"), 10)
            self.assertEqual(denied_power["error_code"], "POWER_UNSUPPORTED")
            # Exceptions raised by drive_check_fn must also fail closed (never propagate unhandled)
            err_probe = probe_platform_durability(sub, drive_check_fn=lambda _r: (_ for _ in ()).throw(RuntimeError("drive_io")))
            self.assertFalse(err_probe["supported"])

    def test_r05_forget_restore_modify_receipt_and_token_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = ShadowMarkdownStore(tmp, synthetic=True)
            self.assertEqual(s.execute(write_req("t1", "v1 md body"), ctx("alice"), 10)["outcome"], "ok")
            self.assertEqual(s.execute(write_req("t2", "v2 md body", kind="Write.modify", node_id="node-1", expected_revision=1), ctx("alice"), 11)["historical_receipt"]["revision"], 2)
            md1 = next((pathlib.Path(tmp) / "nodes").rglob("rev_000001.md")).read_text(encoding="utf-8")
            md2 = next((pathlib.Path(tmp) / "nodes").rglob("rev_000002.md")).read_text(encoding="utf-8")
            self.assertEqual(md1, "v1 md body")
            self.assertEqual(md2, "v2 md body")
            self.assertEqual(s.execute({"kind": "Govern.forget", "caller_token": "tg1", "node_id": "node-1", "expected_revision": 2, "reason": "retire"}, ctx("alice"), 12)["target"]["projection"], "tombstoned")
            self.assertEqual(s.execute(write_req("t1", "reuse attempt"), ctx("alice"), 13)["error_code"], "TOKEN_PAYLOAD_CONFLICT")
            rcpt = s.execute({"kind": "Read.receipt", "operation": "Write.create", "caller_token": "t1"}, ctx("alice"), 14)
            self.assertEqual(rcpt["target"]["commit_status"], "committed")
            self.assertEqual(rcpt["target"]["projection"], "unknown")
            # Forged/tampered verification proof MUST NOT unlock restore!
            self.assertFalse(s.verify_record(node_id="node-1", expected_revision=2, verifier_id="author-1", scope="restore", method_allowed=True, credential_exists=True, credential_time=5, verified_at=15))
            self.assertTrue(s.verify_record(node_id="node-1", expected_revision=2, verifier_id="auditor-1", scope="restore", method_allowed=True, credential_exists=True, credential_time=5, verified_at=15))
            vp = next((pathlib.Path(tmp) / "verifications").glob("*.json"))
            tampered_vp = json.loads(vp.read_text(encoding="utf-8"))
            tampered_vp["verifier_id"] = "author-1"
            vp.write_text(json.dumps(tampered_vp), encoding="utf-8")
            self.assertEqual(s.execute({"kind": "Govern.restore", "caller_token": "tg2-tamper", "node_id": "node-1", "expected_revision": 2, "reason": "forged"}, ctx("alice"), 15)["error_code"], "VERIFICATION_REQUIRED")
            # Even tampering an optional field without recomputing proof_sha (keeping verifier != author-1) MUST fail!
            self.assertTrue(s.verify_record(node_id="node-1", expected_revision=2, verifier_id="auditor-1", scope="restore", method_allowed=True, credential_exists=True, credential_time=5, verified_at=15))
            tampered_sha = json.loads(vp.read_text(encoding="utf-8"))
            tampered_sha["verified_at"] = 99
            vp.write_text(json.dumps(tampered_sha), encoding="utf-8")
            self.assertEqual(s.execute({"kind": "Govern.restore", "caller_token": "tg2-tamper-sha", "node_id": "node-1", "expected_revision": 2, "reason": "forged-sha"}, ctx("alice"), 15)["error_code"], "VERIFICATION_REQUIRED")
            # Re-verify properly -> restore succeeds
            self.assertTrue(s.verify_record(node_id="node-1", expected_revision=2, verifier_id="auditor-1", scope="restore", method_allowed=True, credential_exists=True, credential_time=5, verified_at=15))
            self.assertEqual(s.execute({"kind": "Govern.restore", "caller_token": "tg2", "node_id": "node-1", "expected_revision": 2, "reason": "re-enable"}, ctx("alice"), 16)["target"]["projection"], "active")

    def test_r06_index_delete_corrupt_fail_closed_and_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = ShadowMarkdownStore(tmp, synthetic=True)
            self.assertEqual(s.execute(write_req("t1", "rebuildable index body"), ctx("alice"), 10)["outcome"], "ok")
            idx_path = pathlib.Path(tmp) / "index/inverted.json"
            # Both corrupt AND deleted index MUST fail closed (INTEGRITY_FAILURE)
            idx_path.write_text("{corrupt", encoding="utf-8")
            self.assertEqual(s.execute({"kind": "Read.search", "query": "rebuildable", "limit": 5, "include_provenance": False, "condition_query": cspace(), "time_axis": "effective", "time_point": Q}, ctx("alice"), 11)["error_code"], "INTEGRITY_FAILURE")
            idx_path.unlink()
            self.assertEqual(s.execute({"kind": "Read.search", "query": "rebuildable", "limit": 5, "include_provenance": False, "condition_query": cspace(), "time_axis": "effective", "time_point": Q}, ctx("alice"), 11)["error_code"], "INTEGRITY_FAILURE")
            s.rebuild_index()
            good = s.execute({"kind": "Read.search", "query": "rebuildable", "limit": 5, "include_provenance": False, "condition_query": cspace(), "time_axis": "effective", "time_point": Q}, ctx("alice"), 12)
            self.assertEqual(good["outcome"], "ok")
            self.assertEqual(good["records"][0]["body"], "rebuildable index body")

    def test_r07_audit_missing_truncated_utf8_payload_leak_and_bool_seq(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = ShadowMarkdownStore(tmp, synthetic=True)
            res = s.execute(write_req("t1", "audit isolation body"), ctx("alice"), 10)
            self.assertEqual(res["outcome"], "ok")
            audit_p = pathlib.Path(tmp) / "audit/audit.jsonl"
            orig_audit = audit_p.read_bytes()

            # 1. Missing audit -> commit_status STILL committed, audit_state=missing, and Govern replay also reports AUDIT_INCOMPLETE
            audit_p.unlink()
            rec_missing = s.recover_token_state(tenant="t1", principal="alice", operation="Write.create", caller_token="t1")
            self.assertEqual(rec_missing["commit_status"], "committed")
            self.assertEqual(rec_missing["audit_state"], "missing")

            # 2. Truncated tail without newline & malformed tail with newline -> degraded
            audit_p.write_bytes(orig_audit[:-1])
            self.assertEqual(inspect_audit(audit_p)["state"], "degraded")
            audit_p.write_bytes(orig_audit + b'{"seq":99\n')
            self.assertEqual(inspect_audit(audit_p)["state"], "degraded")

            # 3. Invalid UTF-8 in middle line -> integrity_failure (never uncaught UnicodeDecodeError!)
            audit_p.write_bytes(b"\xff\xfe\n" + orig_audit)
            self.assertEqual(inspect_audit(audit_p)["state"], "integrity_failure")

            # 4. Payload leak -> explicitly classified as payload_leak_in_audit
            row = json.loads(orig_audit.decode("utf-8").splitlines()[0])
            leaked = dict(row, content="secret body")
            audit_p.write_bytes((json.dumps(leaked) + "\n").encode("utf-8"))
            leak_info = inspect_audit(audit_p)
            self.assertEqual(leak_info["state"], "integrity_failure")
            self.assertEqual(leak_info["reason"], "payload_leak_in_audit")

            # 5. Boolean seq=True with recomputed entry_sha -> MUST still fail strictly as invalid_audit_schema
            bool_seq = {k: v for k, v in row.items() if k != "entry_sha"}
            bool_seq["seq"] = True
            bool_seq["entry_sha"] = hashlib.sha256(canonical(bool_seq)).hexdigest()
            audit_p.write_bytes((json.dumps(bool_seq) + "\n").encode("utf-8"))
            self.assertEqual(inspect_audit(audit_p)["state"], "integrity_failure")

            # 6. Foreign tenant row -> integrity_failure
            audit_p.write_bytes(orig_audit)
            self.assertEqual(inspect_audit(audit_p, expected_tenant="t2")["state"], "integrity_failure")

    def test_r08_immutable_revision_refuses_overwrite_on_write_and_correct_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = ShadowMarkdownStore(tmp, synthetic=True)
            self.assertEqual(s.execute(write_req("t1", "v1"), ctx("alice"), 10)["outcome"], "ok")
            mp = pathlib.Path(tmp) / "manifest.json"
            m = json.loads(mp.read_text(encoding="utf-8"))
            m["node_seq"] = 0
            body = {k: v for k, v in m.items() if k != "manifest_sha"}
            m["manifest_sha"] = hashlib.sha256(canonical(body)).hexdigest()
            mp.write_text(json.dumps(m), encoding="utf-8")
            bad = s.execute(write_req("t2", "overwrite attempt"), ctx("alice"), 11)
            self.assertEqual(bad["error_code"], "INTEGRITY_FAILURE")
            self.assertEqual(next((pathlib.Path(tmp) / "nodes").rglob("rev_000001.md")).read_text(encoding="utf-8"), "v1")
            # Pre-existing rev_000002.md blocks Govern.correct_revision from overwriting immutable file
            rev2_md = next((pathlib.Path(tmp) / "nodes").rglob("rev_000001.md")).parent / "rev_000002.md"
            rev2_md.write_text("already-there", encoding="utf-8")
            rep = {k: v for k, v in write_req("unused", "overwrite rev2").items() if k not in ("kind", "caller_token", "durability_request")}
            bad_cor = s.execute({"kind": "Govern.correct_revision", "caller_token": "tg-ov", "node_id": "node-1", "expected_revision": 1, "reason": "fix", "replacement": rep}, ctx("alice"), 12)
            self.assertEqual(bad_cor["error_code"], "INTEGRITY_FAILURE")
            self.assertEqual(rev2_md.read_text(encoding="utf-8"), "already-there")

    def test_missing_manifest_with_stored_records_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp_truth:
            s = ShadowMarkdownStore(tmp_truth, synthetic=True)
            self.assertEqual(s.execute(write_req("truth", "manifest truth body"), ctx("alice"), 10)["outcome"], "ok")
            (pathlib.Path(tmp_truth) / "manifest.json").unlink()
            with self.assertRaisesRegex(ValueError, "missing manifest with stored records"):
                ShadowMarkdownStore(tmp_truth, synthetic=True).recover_token_state(tenant="t1", principal="alice", operation="Write.create", caller_token="truth")
        with tempfile.TemporaryDirectory() as tmp_intent:
            s = ShadowMarkdownStore(tmp_intent, synthetic=True)
            def crash_after_intent(stage, _path):
                if stage == "intent:after_replace":
                    raise InjectedCrash(stage)
            with self.assertRaises(InjectedCrash):
                s.execute(write_req("intent-only", "not-published"), ctx("alice"), 10, fault_hook=crash_after_intent)
            (pathlib.Path(tmp_intent) / "manifest.json").unlink()
            with self.assertRaisesRegex(ValueError, "missing manifest with stored records"):
                ShadowMarkdownStore(tmp_intent, synthetic=True).recover_token_state(tenant="t1", principal="alice", operation="Write.create", caller_token="intent-only")
        with tempfile.TemporaryDirectory() as tmp_cancel:
            s = ShadowMarkdownStore(tmp_cancel, synthetic=True)
            self.assertEqual(s.execute({"kind": "Operation.cancel", "target_operation": "Write.create", "caller_token": "cancel-only", "fencing_epoch": 2, "reason": "abort"}, ctx("alice"), 10)["error_code"], "CANCELLED")
            self.assertNotIn("manifest.json", {path.name for path in pathlib.Path(tmp_cancel).glob("manifest.json")})
            self.assertEqual(s.execute(write_req("cancel-only", "late body"), ctx("alice"), 11)["error_code"], "CANCELLED")

    def test_review_verify_recovers_before_creating_proof(self):
        for point, committed in (("meta:after_replace", False), ("manifest:after_replace", True)):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as tmp:
                store = ShadowMarkdownStore(tmp, synthetic=True)
                def crash(stage, _path):
                    if stage == point:
                        raise InjectedCrash(stage)
                with self.assertRaises(InjectedCrash):
                    store.execute(write_req("verify-first", "fixture body"), ctx(), 10, fault_hook=crash)
                reopened = ShadowMarkdownStore(tmp, synthetic=True)
                result = reopened.verify_record(node_id="node-1", expected_revision=1, verifier_id="fixture-reviewer",
                                                scope="restore", method_allowed=True, credential_exists=True,
                                                credential_time=5, verified_at=11)
                root = pathlib.Path(tmp)
                self.assertIs(result, committed)
                self.assertEqual(len(list((root / "verifications").glob("*.json"))), int(committed))
                self.assertEqual(len(list((root / "nodes").rglob("*.md"))), int(committed))
                self.assertEqual(reopened.recover_token_state(tenant="t1", principal="alice",
                                 operation="Write.create", caller_token="verify-first")["commit_status"],
                                 "committed" if committed else "unknown")

    def test_review_rollback_checks_all_evidence_before_disk_mutation(self):
        for conflict in ("committed_token", "body_digest"):
            with self.subTest(conflict=conflict), tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                store = ShadowMarkdownStore(tmp, synthetic=True)
                before = {}
                def checkpoint(stage, _path):
                    if stage == "manifest:before_replace":
                        mp = root / "manifest.json"
                        ip = next((root / "intents").glob("*.json"))
                        before.update({mp: mp.read_bytes(), ip: ip.read_bytes()})
                        if conflict == "body_digest":
                            raise InjectedCrash(stage)
                request = write_req("rollback-guard", "fixture body")
                if conflict == "committed_token":
                    self.assertEqual(store.execute(request, ctx(), 10, fault_hook=checkpoint)["outcome"], "ok")
                    self.assertEqual(len(before), 2)
                    for path, data in before.items():
                        path.write_bytes(data)
                    reason = "token contradicts"
                else:
                    with self.assertRaises(InjectedCrash):
                        store.execute(request, ctx(), 10, fault_hook=checkpoint)
                    body = next((root / "nodes").rglob("*.md"))
                    body.write_bytes(body.read_bytes() + b"!")
                    reason = "body cannot be rolled back"
                def snapshot():
                    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*")
                            if p.is_file() and p.suffix != ".lock"}
                observed = snapshot()
                self.assertEqual(len([p for p in observed if p.startswith("nodes")]), 2)
                with self.assertRaisesRegex(ValueError, reason):
                    ShadowMarkdownStore(tmp, synthetic=True).recover_token_state(
                        tenant="t1", principal="alice", operation="Write.create", caller_token="rollback-guard")
                after = snapshot()
                self.assertEqual(after.keys(), observed.keys())
                self.assertEqual(sorted(p for p in observed if after[p] != observed[p]), [])

    def test_write_manifest_index_crash_recovery(self):
        cases = (
            ("manifest:before_replace", 1, "unknown", False),
            ("manifest:after_replace", 1, "committed", True),
            ("index:before_replace", 1, "committed", True),
            ("audit:after_append", 1, "committed", True),
            ("token:after_replace", 2, "committed", True),
        )
        for idx, (target, occurrence, expected_status, visible) in enumerate(cases):
            with self.subTest(stage=target), tempfile.TemporaryDirectory() as tmp:
                s = ShadowMarkdownStore(tmp, synthetic=True)
                seen = [0]
                def crash_hook(stage, _path):
                    if stage == target:
                        seen[0] += 1
                        if seen[0] == occurrence:
                            raise InjectedCrash(stage)
                with self.assertRaises(InjectedCrash):
                    s.execute(write_req("t-crash-%d" % idx, "crash-visible-body"), ctx("alice"), 10, fault_hook=crash_hook)
                reopened = ShadowMarkdownStore(tmp, synthetic=True)
                recovered = reopened.recover_token_state(tenant="t1", principal="alice", operation="Write.create", caller_token="t-crash-%d" % idx)
                self.assertEqual(recovered["commit_status"], expected_status)
                if visible:
                    manifest = reopened._load_manifest_or_init()
                    self.assertEqual(manifest["nodes"]["node-1"]["active_revision"], 1)
                    self.assertIsNotNone(reopened._load_valid_index(manifest))
                    self.assertEqual(inspect_audit(pathlib.Path(tmp) / "audit/audit.jsonl")["count"], 1)
                    read = reopened.execute({"kind": "Read.get", "node_id": "node-1", "include_provenance": False,
                                             "condition_query": cspace(), "time_axis": "effective", "time_point": Q}, ctx("alice"), 11)
                    self.assertEqual(read["records"][0]["body"], "crash-visible-body")
                else:
                    manifest = reopened._load_manifest_or_init()
                    self.assertNotIn("node-1", manifest["nodes"])
                    self.assertEqual(list((pathlib.Path(tmp) / "nodes").rglob("rev_*.md")), [])
                    self.assertFalse((pathlib.Path(tmp) / "audit/audit.jsonl").exists())

    def test_govern_meta_crash_before_manifest_rolls_back(self):
        for action in ("forget", "restore", "change_policy", "correct_revision"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as tmp:
                s = ShadowMarkdownStore(tmp, synthetic=True)
                self.assertEqual(s.execute(write_req("base", "govern source"), ctx("alice"), 10)["outcome"], "ok")
                revision = 1
                original_state = "active"
                if action == "restore":
                    self.assertEqual(s.execute({"kind": "Govern.forget", "caller_token": "setup-forget", "node_id": "node-1", "expected_revision": 1, "reason": "setup"}, ctx("alice"), 11)["target"]["projection"], "tombstoned")
                    self.assertTrue(s.verify_record(node_id="node-1", expected_revision=1, verifier_id="auditor-1", scope="restore", method_allowed=True, credential_exists=True, credential_time=5, verified_at=12))
                    original_state = "tombstoned"
                request = {"kind": "Govern." + action, "caller_token": "crash-" + action, "node_id": "node-1", "expected_revision": revision, "reason": "inject crash"}
                if action == "change_policy":
                    request.update({"declared_sensitivity": 2, "reader_ceiling": ["alice"]})
                if action == "correct_revision":
                    rep = {k: v for k, v in write_req("unused", "corrected body").items() if k not in ("kind", "caller_token", "durability_request")}
                    request["replacement"] = rep
                def crash_hook(stage, _path):
                    if stage == "meta:after_replace":
                        raise InjectedCrash(stage)
                with self.assertRaises(InjectedCrash):
                    s.execute(request, ctx("alice"), 20, fault_hook=crash_hook)
                reopened = ShadowMarkdownStore(tmp, synthetic=True)
                recovered = reopened.recover_token_state(tenant="t1", principal="alice", operation=request["kind"], caller_token=request["caller_token"])
                self.assertEqual(recovered["commit_status"], "unknown")
                manifest = reopened._load_manifest_or_init()
                self.assertEqual(manifest["nodes"]["node-1"]["active_revision"], 1)
                self.assertEqual(manifest["nodes"]["node-1"]["state"], original_state)
                nodes, metas = reopened._build_graph_nodes(manifest)
                self.assertEqual(metas["node-1"]["state"], original_state)
                if action == "change_policy":
                    self.assertEqual(metas["node-1"]["declared_sensitivity"], 1)
                    self.assertEqual(metas["node-1"]["current_readers"], ["alice", "bob"])
                if action == "correct_revision":
                    self.assertFalse(reopened._md_path("node-1", 2).exists())
                    self.assertFalse(reopened._meta_path("node-1", 2).exists())
                self.assertEqual(inspect_audit(pathlib.Path(tmp) / "audit/audit.jsonl")["count"], 2 if action == "restore" else 1)

    def test_govern_manifest_commit_crash_rolls_forward(self):
        for action in ("forget", "restore", "change_policy", "correct_revision"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as tmp:
                s = ShadowMarkdownStore(tmp, synthetic=True)
                self.assertEqual(s.execute(write_req("base", "govern committed source"), ctx("alice"), 10)["outcome"], "ok")
                setup_audits = 1
                if action == "restore":
                    self.assertEqual(s.execute({"kind": "Govern.forget", "caller_token": "setup-forget", "node_id": "node-1", "expected_revision": 1, "reason": "setup"}, ctx("alice"), 11)["target"]["projection"], "tombstoned")
                    self.assertTrue(s.verify_record(node_id="node-1", expected_revision=1, verifier_id="auditor-1", scope="restore", method_allowed=True, credential_exists=True, credential_time=5, verified_at=12))
                    setup_audits = 2
                request = {"kind": "Govern." + action, "caller_token": "commit-" + action, "node_id": "node-1", "expected_revision": 1, "reason": "commit then crash"}
                expected_revision, expected_state = 1, ("tombstoned" if action == "forget" else "active")
                if action == "change_policy":
                    request.update({"declared_sensitivity": 2, "reader_ceiling": ["alice"]})
                if action == "correct_revision":
                    rep = {k: v for k, v in write_req("unused", "corrected committed body").items() if k not in ("kind", "caller_token", "durability_request")}
                    request["replacement"] = rep
                    expected_revision = 2
                def crash_hook(stage, _path):
                    if stage == "manifest:after_replace":
                        raise InjectedCrash(stage)
                with self.assertRaises(InjectedCrash):
                    s.execute(request, ctx("alice"), 20, fault_hook=crash_hook)
                reopened = ShadowMarkdownStore(tmp, synthetic=True)
                recovered = reopened.recover_token_state(tenant="t1", principal="alice", operation=request["kind"], caller_token=request["caller_token"])
                self.assertEqual(recovered["commit_status"], "committed")
                manifest = reopened._load_manifest_or_init()
                self.assertEqual(manifest["nodes"]["node-1"]["active_revision"], expected_revision)
                self.assertEqual(manifest["nodes"]["node-1"]["state"], expected_state)
                self.assertIsNotNone(reopened._load_valid_index(manifest))
                nodes, metas = reopened._build_graph_nodes(manifest)
                self.assertEqual(metas["node-1"]["state"], expected_state)
                if action == "change_policy":
                    self.assertEqual(metas["node-1"]["declared_sensitivity"], 2)
                    self.assertEqual(metas["node-1"]["current_readers"], ["alice"])
                if action == "correct_revision":
                    self.assertEqual(metas["node-1"]["state"], "active")
                    self.assertEqual(reopened._md_path("node-1", 2).read_text(encoding="utf-8"), "corrected committed body")
                    self.assertEqual(reopened._read_meta_verified(reopened._meta_path("node-1", 1))["state"], "superseded")
                self.assertEqual(inspect_audit(pathlib.Path(tmp) / "audit/audit.jsonl")["count"], setup_audits + 1)

    def test_meta_source_edges_roundtrip_through_seal_and_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = ShadowMarkdownStore(tmp, synthetic=True)
            self.assertEqual(s.execute(write_req("t-source", "source body"), ctx("alice"), 10)["outcome"], "ok")
            edge = {"node_id": "node-1", "relation": "derived", "revision": 1,
                    "content_sha": hashlib.sha256(b"source body").hexdigest()}
            request = write_req("t-derived", "derived body")
            request["source_edges"] = [edge]
            self.assertEqual(s.execute(request, ctx("alice"), 11)["outcome"], "ok")
            nodes, metas = s._build_graph_nodes(s._load_manifest_or_init())
            self.assertEqual(metas["node-2"]["source_edges"], [edge])
            self.assertEqual(nodes["node-2"].edges[0].target, "node-1")

    def test_selfcheck_never_reports_unimplemented_checks_as_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = ShadowMarkdownStore(tmp, synthetic=True)
            response = s.execute({
                "kind": "SelfCheck", "check_ids": ["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C10"],
                "scope": "isolated-runtime", "snapshot_ref": "snap-1",
            }, ctx("alice"), 10)
            self.assertEqual(response["outcome"], "unknown")
            self.assertEqual(response["error_code"], "CONDITION_DEFERRED")
            self.assertEqual(response["next_action"], "refresh_snapshot")
            self.assertEqual(response["selfcheck_aggregate"], "NOT_RUN")
            self.assertNotEqual(response["selfcheck_aggregate"], "PASS")

    def test_meta_checksum_and_manifest_state_binding_fail_closed(self):
        read_req = {"kind": "Read.get", "node_id": "node-1", "include_provenance": False,
                    "condition_query": cspace(), "time_axis": "effective", "time_point": Q}
        for name, alter in (
            ("missing_meta_sha", lambda meta: meta.pop("meta_sha", None)),
            ("modified_reader_list", lambda meta: meta["current_readers"].append("mallory")),
            ("modified_state_without_reseal", lambda meta: meta.__setitem__("state", "tombstoned")),
            ("resealed_state_diverges_from_manifest", lambda meta: (
                meta.__setitem__("state", "tombstoned"),
                meta.__setitem__("meta_sha", hashlib.sha256(canonical({k: v for k, v in meta.items() if k != "meta_sha"})).hexdigest()),
            )),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                s = ShadowMarkdownStore(tmp, synthetic=True)
                self.assertEqual(s.execute(write_req("t-meta", "integrity body"), ctx("alice"), 10)["outcome"], "ok")
                meta_path = s._meta_path("node-1", 1)
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                alter(meta)
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, sort_keys=True), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "INTEGRITY_FAILURE"):
                    s.execute(read_req, ctx("alice"), 11)
                recovered = s.recover_token_state(tenant="t1", principal="alice", operation="Write.create", caller_token="t-meta")
                self.assertEqual(recovered["commit_status"], "unknown")
                self.assertTrue(recovered["integrity_failure"])

    def test_meta_checksum_survives_policy_and_revision_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = ShadowMarkdownStore(tmp, synthetic=True)
            self.assertEqual(s.execute(write_req("t-policy-base", "policy body"), ctx("alice"), 10)["outcome"], "ok")
            policy = s.execute({"kind": "Govern.change_policy", "caller_token": "t-policy", "node_id": "node-1", "expected_revision": 1, "reason": "tighten", "declared_sensitivity": 2, "reader_ceiling": ["alice"]}, ctx("alice"), 11)
            self.assertEqual(policy["outcome"], "ok")
            s._build_graph_nodes(s._load_manifest_or_init())

        with tempfile.TemporaryDirectory() as tmp:
            s = ShadowMarkdownStore(tmp, synthetic=True)
            self.assertEqual(s.execute(write_req("t-rev-base", "old body"), ctx("alice"), 10)["outcome"], "ok")
            rep = {k: v for k, v in write_req("unused", "new body").items() if k not in ("kind", "caller_token", "durability_request")}
            corrected = s.execute({"kind": "Govern.correct_revision", "caller_token": "t-rev", "node_id": "node-1", "expected_revision": 1, "reason": "correct typo", "replacement": rep}, ctx("alice"), 11)
            self.assertEqual(corrected["outcome"], "ok")
            s._build_graph_nodes(s._load_manifest_or_init())
            old = s.recover_token_state(tenant="t1", principal="alice", operation="Write.create", caller_token="t-rev-base")
            self.assertEqual(old["commit_status"], "committed")

    def test_r09_lock_busy_cross_process_and_query_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = ShadowMarkdownStore(tmp, synthetic=True, lock_timeout_s=0.1)
            for i in range(15):
                self.assertEqual(s.execute(write_req(f"t-{i}", f"item {i} benchmark memory"), ctx("alice"), 10 + i)["outcome"], "ok")
            t0 = time.monotonic()
            r = s.execute({"kind": "Read.search", "query": "benchmark memory", "limit": 5, "include_provenance": False, "condition_query": cspace(), "time_axis": "effective", "time_point": Q}, ctx("alice"), 30)
            elapsed = time.monotonic() - t0
            self.assertEqual(r["outcome"], "ok")
            self.assertEqual(len(r["records"]), 5)
            self.assertLess(elapsed, 2.0)

            holder_py = pathlib.Path(tmp) / "holder.py"
            holder_py.write_text(
                "import pathlib, sys, time\n"
                "sys.path.insert(0, sys.argv[1])\n"
                "from shadow_runtime.durability import ExclusiveFileLock\n"
                "with ExclusiveFileLock(pathlib.Path(sys.argv[2]), timeout_s=2.0):\n"
                "    pathlib.Path(sys.argv[3]).write_text('LOCKED', encoding='utf-8')\n"
                "    time.sleep(0.8)\n",
                encoding="utf-8",
            )
            ready_flag = pathlib.Path(tmp) / "locked.flag"
            lp = pathlib.Path(tmp) / "locks/write.lock"
            env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
            hp = subprocess.Popen([sys.executable, "-X", "utf8", "-B", str(holder_py), str(ROOT), str(lp), str(ready_flag)], env=env)
            try:
                deadline = time.monotonic() + 5.0
                while not ready_flag.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready_flag.exists())
                from shadow_runtime.durability import ExclusiveFileLock, LockBusyError
                with self.assertRaises(LockBusyError):
                    with ExclusiveFileLock(lp, timeout_s=0.1):
                        pass
            finally:
                hp.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
