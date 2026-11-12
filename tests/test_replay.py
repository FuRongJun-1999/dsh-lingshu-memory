import copy
import unittest
from sandbox_runtime.replay import Replay
from sandbox_runtime.controller import digest
from test_sandbox_controller import loop, task


def event(seq,kind,payload=None,**kwargs):
    e=dict(id="event-%d"%seq,seq=seq,stream="stream-a",session="session-a",kind=kind,payload={} if payload is None else payload,task_sha=digest(payload["task"]) if payload is not None and "task" in payload else digest(task()))
    e.update(kwargs);return e


def replay(t=None):
    c,p,identity,time,alerts=loop();r=Replay(c,stream="stream-a",session="session-a",bootstrap_task=task() if t is None else t)
    r.handle(event(1,"task/start",dict(task=task() if t is None else t)))
    return r,p,identity,time,alerts


class ReplayTests(unittest.TestCase):
 def test_start_assemble_decision_runs_real_controller(self):
    r,p,_,_,_=replay();self.assertEqual(r.handle(event(2,"system-prompt/assemble"))["status"],"prepared")
    out=r.handle(event(3,"decision"));self.assertEqual(out["status"],"ready")
    self.assertEqual(out["records"][0]["body"],"blue widget limit 8")
    self.assertEqual(r.spent,dict(calls=5,bytes=57));self.assertEqual(len(p.events),5)

 def test_duplicate_decision_is_metadata_only_without_work(self):
    r,p,_,_,_=replay();r.handle(event(2,"system-prompt/assemble"));d=event(3,"decision");r.handle(d)
    self.assertEqual(r.handle(d),{"status":"duplicate"});self.assertEqual(len(p.events),5)
    self.assertNotIn("body",str(r.receipts))

 def test_id_collision_invalidates_ticket_requires_resume(self):
    r,_,_,_,_=replay();r.handle(event(2,"system-prompt/assemble"))
    self.assertEqual(r.handle(event(2,"decision")),{"status":"blocked","reason":"EVENT_COLLISION"})
    self.assertEqual(r.handle(event(3,"decision")),{"status":"blocked","reason":"DESYNC"})
    self.assertEqual(r.handle(event(4,"session/resume",dict(task=task())))["status"],"prepared")
    self.assertEqual(r.handle(event(5,"decision"))["status"],"ready")

 def test_gap_wrong_order_and_resume_highwater(self):
    r,_,_,_,_=replay();r.handle(event(2,"system-prompt/assemble"))
    self.assertEqual(r.handle(event(5,"decision")),{"status":"blocked","reason":"EVENT_ORDER"})
    self.assertEqual(r.handle(event(4,"session/resume",dict(task=task()))),{"status":"blocked","reason":"DESYNC"})
    self.assertEqual(r.handle(event(6,"session/resume",dict(task=task())))["status"],"prepared")
    self.assertEqual(r.handle(event(7,"decision"))["status"],"ready")

 def test_compact_discards_ticket_and_resume_retrieves(self):
    r,p,_,_,_=replay();r.handle(event(2,"system-prompt/assemble"));old=r.ticket
    self.assertEqual(r.handle(event(3,"context/compact")),{"status":"compacted"});self.assertIsNone(r.ticket);self.assertIsNone(r.work)
    self.assertEqual(r.handle(event(4,"decision")),{"status":"blocked","reason":"NOT_PREPARED"})
    self.assertEqual(r.handle(event(5,"session/resume",dict(task=task())))["status"],"prepared")
    self.assertIsNot(r.ticket,old);self.assertEqual(len(p.events),8)
    self.assertEqual(r.handle(event(6,"decision"))["status"],"ready")

 def test_resume_mismatch_does_not_replace_current_task(self):
    r,_,_,_,_=replay();r.handle(event(2,"context/compact"))
    self.assertEqual(r.handle(event(3,"session/resume",dict(task=task(id="other")))),{"status":"blocked","reason":"RESUME_MISMATCH"})
    self.assertEqual(r.task["id"],"task-a")

 def test_budget_carries_across_assemble_compact_resume(self):
    t=task(budget=dict(calls=8,bytes=20000,retries=1));r,_,_,_,_=replay(t)
    r.handle(event(2,"system-prompt/assemble",task_sha=digest(t)));r.handle(event(3,"context/compact",task_sha=digest(t)))
    r.handle(event(4,"session/resume",dict(task=t)))
    self.assertEqual(r.handle(event(5,"decision",task_sha=digest(t))),{"status":"blocked","reason":"BUDGET"})
    self.assertEqual(r.spent["calls"],8)

 def test_byte_budget_carries_across_events(self):
    t=task(budget=dict(calls=64,bytes=70,retries=1));r,_,_,_,_=replay(t)
    r.handle(event(2,"system-prompt/assemble",task_sha=digest(t)));r.handle(event(3,"context/compact",task_sha=digest(t)));r.handle(event(4,"session/resume",dict(task=t)))
    self.assertEqual(r.handle(event(5,"decision",task_sha=digest(t))),{"status":"blocked","reason":"BUDGET"})

 def test_revision_rollback_and_task_switch_cannot_reuse_evidence(self):
    r,_,_,_,_=replay();r.handle(event(2,"system-prompt/assemble"))
    self.assertEqual(r.handle(event(3,"task/start",dict(task=task(id="other"))))["status"],"started")
    self.assertEqual(r.handle(event(4,"decision",task_sha=digest(task(id="other")))),{"status":"blocked","reason":"NOT_PREPARED"})
    self.assertEqual(r.handle(event(5,"task/start",dict(task=task()))),{"status":"blocked","reason":"TASK_REVISION"})

 def test_new_revision_resets_budget_but_not_same_revision(self):
    t=task(budget=dict(calls=4,bytes=20000,retries=1));r,_,_,_,_=replay(t)
    r.handle(event(2,"system-prompt/assemble",task_sha=digest(t)));r.handle(event(3,"decision",task_sha=digest(t)))
    self.assertEqual(r.spent["calls"],4)
    self.assertEqual(r.handle(event(4,"task/start",dict(task=task(revision=2))))["status"],"started")
    self.assertEqual(r.spent,dict(calls=0,bytes=0))

 def test_context_changes_during_prepare_decision_and_resume(self):
    r,_,ctx,_,_=replay();r.handle(event(2,"system-prompt/assemble"));ctx["policy_generation"]=2
    self.assertEqual(r.handle(event(3,"decision")),{"status":"blocked","reason":"CONTEXT_CHANGED"})
    r.handle(event(4,"session/resume",dict(task=task())))
    self.assertEqual(r.handle(event(5,"decision"))["status"],"ready")

 def test_foreign_stream_session_malformed_unknown_revoke(self):
    for e in [event(3,"decision",session="other"),event(3,"decision",stream="old"),event(3,"bogus"),event(True,"decision"),event(3,"decision",dict(body="inject")),dict(kind="decision")]:
        r,_,_,_,_=replay();r.handle(event(2,"system-prompt/assemble"));out=r.handle(e)
        self.assertEqual(out["status"],"blocked");self.assertIsNone(r.ticket)

 def test_close_and_fresh_process_do_not_restore_tickets(self):
    r,_,_,_,_=replay();r.handle(event(2,"system-prompt/assemble"));r.handle(event(3,"session/close"))
    self.assertEqual(r.handle(event(4,"decision")),{"status":"blocked","reason":"CLOSED"})
    c,_,_,_,_=loop();fresh=Replay(c,stream="new-stream",session="session-a",bootstrap_task=task(revision=2))
    self.assertEqual(fresh.handle(event(1,"decision")),{"status":"blocked","reason":"WRONG_STREAM"})

 def test_event_limit_and_duplicate_no_side_effect_even_at_limit(self):
    r,p,_,_,_=replay();r.seen.update({"fake%d"%i:"sha" for i in range(255)})
    self.assertEqual(r.handle(event(1,"task/start",dict(task=task()))),{"status":"duplicate"})
    self.assertEqual(r.handle(event(2,"system-prompt/assemble")),{"status":"blocked","reason":"EVENT_LIMIT"});self.assertEqual(p.events,[])

 def test_review_metadata_only_duplicate_is_not_an_ack(self):
    r,_,_,_,_=replay()
    self.assertEqual(r.handle(event(1,"task/start")),{"status":"blocked","reason":"EVENT_COLLISION"})

 def test_review_exception_reserves_remaining_work_budget(self):
    r,p,_,_,_=replay();old=r.controller.store.search
    def faulty(*args,**kwargs):
        old(*args,**kwargs);raise OSError("after actual call")
    r.controller.store.search=faulty
    r.handle(event(2,"system-prompt/assemble"))
    self.assertEqual(r.spent,dict(calls=64,bytes=20000))
    r.handle(event(3,"system-prompt/assemble"))
    self.assertEqual(r.handle(event(4,"decision")),{"status":"blocked","reason":"BUDGET"})
    self.assertEqual(len(p.events),1)

 def test_review_restart_requires_trusted_bootstrap_task_hash(self):
    c,_,_,_,_=loop();r=Replay(c,stream="new",session="session-a",bootstrap_task=task(revision=2))
    old=event(1,"task/start",dict(task=task()),stream="new")
    self.assertEqual(r.handle(old),{"status":"blocked","reason":"BOOTSTRAP_MISMATCH"})

 def test_fresh_stream_bootstrap_retrieves_not_serialized_ticket(self):
    c,p,_,_,_=loop();r=Replay(c,stream="new",session="session-a",bootstrap_task=task(revision=2))
    for seq,kind,payload in [(1,"task/start",dict(task=task(revision=2))),(2,"system-prompt/assemble",{}),(3,"decision",{})]:
        out=r.handle(event(seq,kind,payload,stream="new",task_sha=digest(task(revision=2))))
    self.assertEqual(out["status"],"ready");self.assertEqual(len(p.events),5)

 def test_delayed_old_task_decision_never_consumes_new_task_ticket(self):
    r,p,_,_,_=replay();r.handle(event(2,"system-prompt/assemble"))
    r.handle(event(3,"task/start",dict(task=task(id="other"))))
    r.handle(event(4,"system-prompt/assemble",task_sha=digest(task(id="other"))))
    self.assertEqual(r.handle(event(5,"decision")),{"status":"blocked","reason":"EVENT_TASK"})
    self.assertIsNone(r.ticket);self.assertEqual(len(p.events),8)

 def test_envelope_task_sha_must_match_payload_task(self):
    r,_,_,_,_=replay()
    self.assertEqual(r.handle(event(2,"task/start",dict(task=task(revision=2)),task_sha=digest(task()))),{"status":"blocked","reason":"EVENT_TASK"})
