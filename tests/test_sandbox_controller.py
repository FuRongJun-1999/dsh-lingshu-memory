import copy
import unittest
from sandbox_runtime.controller import Controller, AlertSink, Ticket
from sandbox_runtime.store import SyntheticStore, Probe
from test_sandbox_store import record, context


def task(**kwargs):
    t=dict(id="task-a",revision=1,query="blue widget",requirements=[dict(key="widget.limit",architecture="widget",version="v1",conditions={"region":"east"})],budget=dict(calls=64,bytes=20000,retries=1))
    t.update(kwargs);return t


def loop(rows=None):
    probe=Probe();store=SyntheticStore([record()] if rows is None else rows,synthetic=True,probe=probe)
    identity=context();time=[1];alerts=AlertSink()
    c=Controller(store,probe,context_provider=lambda:copy.deepcopy(identity),clock=lambda:time[0],alerts=alerts)
    return c,probe,identity,time,alerts


class ControllerTests(unittest.TestCase):
    def test_run_performs_search_read_key_confirmation_and_recheck(self):
        c,p,_,_,a=loop();out=c.run(task())
        self.assertEqual(out["status"],"ready")
        self.assertEqual(out["records"][0]["body"],"blue widget limit 8")
        self.assertEqual([x["operation"] for x in p.events],["search","get","search","get","get"])
        self.assertEqual(len({x["request_id"] for x in p.events}),5)
        self.assertEqual(a.events,[])

    def test_actual_refetch_after_irrelevant_initial_query(self):
        c,p,_,_,_=loop();out=c.run(task(query="unrelatedword"))
        self.assertEqual(out["status"],"ready")
        self.assertEqual([x["operation"] for x in p.events],["search","search","get","get"])
        self.assertEqual(p.events[0]["returned"],0)
        self.assertEqual(p.events[1]["mode"],"key")

    def test_missing_evidence_alert_has_no_partial_facts(self):
        c,p,_,_,a=loop([]);out=c.run(task())
        self.assertEqual(out,{"status":"blocked","reason":"EVIDENCE_GAP"})
        self.assertEqual(a.events,[{"event":"alert","reason":"EVIDENCE_GAP"}])
        self.assertEqual([e["operation"] for e in p.events],["search","search"])

    def test_wrong_version_conditions_architecture_or_unauthorized(self):
        for row in [record(version="old"),record(architecture="other"),record(conditions={"region":"west"}),record(current_readers=[])]:
            c,_,_,_,_=loop([row]);self.assertEqual(c.run(task()),{"status":"blocked","reason":"EVIDENCE_GAP"})

    def test_key_confirmation_catches_conflict_omitted_by_text(self):
        c,_,_,_,_=loop([record(),record("conflict",body="contrary rule")])
        self.assertEqual(c.run(task()),{"status":"blocked","reason":"AMBIGUOUS"})

    def test_output_reauthorizes_all_context_fields_and_expiry(self):
        for key,value in [("principal","q"),("tenant","b"),("clearance",1),("auth_epoch",2),("policy_generation",2),("expires_at",99)]:
            c,_,identity,_,_=loop();t=task();ticket=c.prepare(t);identity[key]=value
            self.assertEqual(c.emit(ticket,t),{"status":"blocked","reason":"CONTEXT_CHANGED"})
        c,_,_,time,_=loop();t=task();k=c.prepare(t);time[0]=100
        self.assertEqual(c.emit(k,t),{"status":"blocked","reason":"CONTEXT_CHANGED"})
        c,_,_,time,_=loop();time[0]=4;t=task();k=c.prepare(t);time[0]=3
        self.assertEqual(c.emit(k,t),{"status":"blocked","reason":"CONTEXT_CHANGED"})

    def test_budget_includes_output_recheck_and_byte_work(self):
        for b in [dict(calls=0,bytes=20000,retries=1),dict(calls=4,bytes=20000,retries=1),dict(calls=64,bytes=38,retries=1)]:
            c,_,_,_,a=loop();self.assertEqual(c.run(task(budget=b)),{"status":"blocked","reason":"BUDGET"});self.assertTrue(a.events)

    def test_ticket_single_use_wrong_task_and_prepare_invalidation(self):
        c,_,_,_,_=loop();t=task();k=c.prepare(t)
        self.assertEqual(c.emit(k,task(id="other")),{"status":"blocked","reason":"TASK_CHANGED"})
        self.assertEqual(c.emit(k,t),{"status":"blocked","reason":"INVALID_TICKET"})
        k=c.prepare(t);c.prepare(task(revision=2))
        self.assertEqual(c.emit(k,t),{"status":"blocked","reason":"INVALID_TICKET"})
        self.assertEqual(c.emit(Ticket(),t),{"status":"blocked","reason":"INVALID_TICKET"})

    def test_missing_store_log_is_unknown_not_accepted(self):
        c,p,_,_,a=loop();p.record=lambda *args,**kwargs:None
        self.assertEqual(c.run(task()),{"status":"blocked","reason":"TRACE_UNKNOWN"})
        self.assertEqual(a.events,[dict(event="alert",reason="TRACE_UNKNOWN")])

    def test_limit_and_missing_key_confirmation_fail_closed(self):
        c,_,_,_,_=loop([record("many%02d"%i) for i in range(64)])
        self.assertEqual(c.run(task(query="unrelatedword")),{"status":"blocked","reason":"CANDIDATE_LIMIT"})
        c,_,_,_,_=loop();out=c.run(task(budget=dict(calls=64,bytes=20000,retries=0)))
        self.assertEqual(out,{"status":"blocked","reason":"KEY_CONFIRMATION_REQUIRED"})

    def test_mutating_task_or_rows_after_prepare_is_rejected(self):
        c,_,_,_,_=loop();t=task();k=c.prepare(t);t["query"]="changed"
        self.assertEqual(c.emit(k,t),{"status":"blocked","reason":"TASK_CHANGED"})
        c,_,_,_,_=loop();t=task();k=c.prepare(t);c.store._records["target"]["body"]="tampered"
        self.assertEqual(c.emit(k,t),{"status":"blocked","reason":"EVIDENCE_CHANGED"})

    def test_task_validation_closed_and_strict(self):
        for bad in [task(extra=True),task(revision=True),task(requirements=[]),task(budget=dict(calls=True,bytes=2,retries=1)),task(requirements=[task()["requirements"][0]]*2)]:
            c,_,_,_,_=loop()
            with self.assertRaises(ValueError):c.prepare(bad)

    def test_noise_with_unknown_locator_recovers_by_explicit_key(self):
        rows=[record("noise%04d"%i,key="noise.%d"%i,body="blue widget") for i in range(500)]+[record("zzz-target")]
        c,p,_,_,_=loop(rows);out=c.run(task())
        self.assertEqual(out["status"],"ready")
        self.assertEqual(out["records"][0]["citation"]["id"],"zzz-target")
        self.assertEqual(p.events[0]["returned"],4)
        self.assertEqual(p.events[5]["mode"],"key")

    def test_second_requirement_failure_discards_all_partial_facts(self):
        c,_,_,_,a=loop();t=task();t["requirements"].append(dict(key="missing",architecture="widget",version="v1",conditions={}))
        self.assertEqual(c.run(t),{"status":"blocked","reason":"EVIDENCE_GAP"})
        self.assertTrue(a.events)

    def test_backend_exception_after_real_call_blocks_and_alerts(self):
        c,_,_,_,a=loop();old=c.store.search
        def faulty(*args,**kwargs):
            old(*args,**kwargs);raise OSError("private backend message")
        c.store.search=faulty
        self.assertEqual(c.run(task()),{"status":"blocked","reason":"BACKEND_UNKNOWN"})
        self.assertEqual(a.events,[dict(event="alert",reason="BACKEND_UNKNOWN")])

    def test_wrong_request_digest_does_not_count_as_action_evidence(self):
        c,p,_,_,_=loop();old=p.record
        def corrupted(operation,**fields):
            fields["result_sha"]="0"*64;old(operation,**fields)
        p.record=corrupted
        self.assertEqual(c.run(task()),{"status":"blocked","reason":"TRACE_UNKNOWN"})

    def test_lost_prior_probe_or_untracked_side_effect_blocks(self):
        for extra in (False,True):
            c,p,_,_,_=loop();t=task();k=c.prepare(t)
            if extra:c.store.search("widget",context(),1)
            else:p.events.pop(0)
            self.assertEqual(c.emit(k,t),{"status":"blocked","reason":"TRACE_UNKNOWN"})

    def test_reported_alert_without_actual_sink_effect_is_unknown(self):
        c,_,_,_,a=loop([]);a.emit=lambda reason:None
        self.assertEqual(c.run(task()),{"status":"blocked","reason":"ALERT_UNKNOWN"})
        self.assertEqual(a.events,[])

    def test_final_readback_log_corruption_cannot_hide_until_next_call(self):
        c,p,_,_,_=loop();t=task();k=c.prepare(t);old=p.record
        def corrupt_final(operation,**fields):
            fields["result_sha"]="0"*64;old(operation,**fields)
        p.record=corrupt_final
        self.assertEqual(c.emit(k,t),{"status":"blocked","reason":"TRACE_UNKNOWN"})

    def test_independent_review_conflicts_beyond_text_top4(self):
        rows=[record("d%d"%i,version="old",body="blue widget") for i in range(4)]
        rows += [record("late-a",body="alternative rule"),record("late-b",revision=2,body="another rule")]
        c,p,_,_,_=loop(rows)
        self.assertEqual(c.run(task()),{"status":"blocked","reason":"AMBIGUOUS"})
        self.assertEqual(p.events[0]["returned"],4)

    def test_independent_review_equal_body_digest_wrong_revision(self):
        c,_,_,_,_=loop();t=task();k=c.prepare(t)
        c._pending[1]["rows"][0]["locator"]["revision"]=2
        self.assertEqual(c.emit(k,t),{"status":"blocked","reason":"EVIDENCE_CHANGED"})

    def test_independent_review_failure_before_any_stdout_fact(self):
        import contextlib
        import io
        for mode in ("log","bytes"):
            c,p,_,_,_=loop();t=task()
            if mode=="bytes":t["budget"]["bytes"]=38
            k=c.prepare(t)
            if mode=="log":p.record=lambda *args,**kwargs:None
            stdout=io.StringIO()
            with contextlib.redirect_stdout(stdout):out=c.emit(k,t)
            self.assertEqual(stdout.getvalue(),"")
            self.assertEqual(out,{"status":"blocked","reason":"TRACE_UNKNOWN" if mode=="log" else "BUDGET"})
