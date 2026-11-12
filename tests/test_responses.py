"""Hand-written response and cancellation expectations, not generator round trips."""
import copy
import unittest
from framework import responses as m
from framework import api

class ResponseTests(unittest.TestCase):
    def test_absence_basis(self):
        self.assertEqual(m.absence_basis(True,True,False,False,True),"fresh_unseen")
        self.assertEqual(m.absence_basis(True,True,False,True,False),"durable_cancel")
        self.assertEqual(m.absence_basis(True,True,True,False,False),"preaccept_rejected")
        for args in [(True,True,False,False,False),(True,True,True,True,False),(True,True,False,True,True),(False,True,False,True,False),(True,False,False,True,False)]:
            self.assertEqual(m.absence_basis(*args),"unassessed")
        with self.assertRaises(ValueError): m.absence_basis(1,True,False,True,False)

    def test_absent_retry_terminal(self):
        self.assertEqual(api.retry_action("absent",True,True,"durable_cancel"),"return_original_cancel")
        self.assertEqual(api.retry_action("absent",True,True,"preaccept_rejected"),"return_original_rejection")
        self.assertEqual(api.retry_action("absent",True,True),"query_only")
        self.assertEqual(api.retry_action("absent",True,True,"fresh_unseen"),"eligible_for_authorized_first_apply")
        self.assertEqual(api.retry_action("absent",False,True,"durable_cancel"),"conflict")
        self.assertEqual(api.retry_action("absent",True,False,"durable_cancel"),"query_only")
        with self.assertRaises(ValueError): api.retry_action("committed",True,True,"durable_cancel")

    def test_cancel_winner(self):
        self.assertEqual(m.cancellation("pending",True,True,True,True),("absent","cancelled","return_original_cancel"))
        self.assertEqual(m.cancellation("committed",True,True,True,False),("committed","committed","return_original"))
        self.assertEqual(m.cancellation("cancelled",True,True,True,True),("absent","cancelled","return_original_cancel"))
        self.assertEqual(m.cancellation("rejected",True,True,True,False),("absent","rejected","return_original_rejection"))

    def test_cancel_sent_not_proven(self):
        for state in ("unseen","pending","cancelled","unknown"):
            self.assertEqual(m.cancellation(state,True,True,True,False),("unknown","unknown","query_same_token"))
        for args in [("pending",False,True,True,True),("pending",True,False,True,True),("committed",True,True,True,True),("rejected",True,True,True,True),("pending",True,True,True,True,True)]:
            self.assertEqual(m.cancellation(*args),("unknown","unknown","query_same_token"))

    def test_cancel_authorize_before_replay(self):
        for state in ("committed","cancelled","pending","rejected"):
            self.assertEqual(m.cancellation(state,True,True,False,True),(None,None,"authenticate"))
        with self.assertRaises(ValueError): m.cancellation("pending",True,True,1,True)

    def test_read_never_fabricates_commit(self):
        for allowed,success,code in [(True,True,None),(True,False,"READ_FAILED"),(False,True,"NOT_FOUND_OR_DENIED")]:
            e=m.read_response("r",allowed,success);self.assertIsNone(e["target"]);self.assertEqual(e["scope"],"read");self.assertEqual(e["error_code"],code)

    def test_committed_audit_matrix(self):
        expected={"ok":("ok",None,"return_original"),"missing":("error","AUDIT_INCOMPLETE","reconcile_audit"),"failed":("error","AUDIT_FAILED","reconcile_audit"),"unknown":("error","AUDIT_UNCERTAIN","reconcile_audit")}
        for scope in ("mutation","receipt"):
            for audit,result in expected.items():
                e=m.target_response("r",scope,"committed",audit,"active",True,True)
                self.assertEqual((e["outcome"],e["error_code"],e["next_action"]),result)
                self.assertEqual(e["target"],dict(commit_status="committed",audit=audit,projection="active",negative_basis="unassessed"))

    def test_absent_response_matrix(self):
        for basis,code,action in [("durable_cancel","CANCELLED","return_original_cancel"),("preaccept_rejected","PREACCEPT_REJECTED","return_original_rejection")]:
            e=m.target_response("r","receipt","absent","missing","active",True,True,basis)
            self.assertEqual(e["error_code"],code);self.assertEqual(e["next_action"],action)
            self.assertEqual(e["target"],dict(commit_status="absent",audit="unknown",projection="unknown",negative_basis=basis))

    def test_unknown_and_integrity_fail_closed(self):
        for status,basis in [("unknown","unassessed"),("absent","unassessed")]:
            e=m.target_response("r","mutation",status,"ok","active",True,True,basis)
            self.assertEqual(e["outcome"],"unknown");self.assertEqual(e["next_action"],"query_same_token")
            self.assertEqual(e["target"],dict(commit_status="unknown",audit="unknown",projection="unknown",negative_basis="unassessed"))
        e=m.target_response("r","receipt","committed","ok","active",True,True,conflict=True)
        self.assertEqual(e["error_code"],"INTEGRITY_FAILURE");self.assertEqual(e["target"]["commit_status"],"unknown")

    def test_receipt_not_content_authorization(self):
        e=m.target_response("r","receipt","committed","ok","tombstoned",True,False)
        self.assertEqual(e["target"]["projection"],"unknown")
        self.assertNotIn("content",e);self.assertNotIn("node_id",e["target"]);self.assertNotIn("content_sha",e["target"])
        e=m.target_response("r","receipt","committed","ok","tombstoned",True,True)
        self.assertEqual(e["target"]["projection"],"tombstoned")

    def test_denied_never_replays_history(self):
        for status in ("committed","absent","unknown"):
            e=m.target_response("r","receipt",status,"ok","active",False,True)
            self.assertIsNone(e["target"]);self.assertEqual(e["error_code"],"NOT_FOUND_OR_DENIED")
        self.assertEqual(m.target_response("r","receipt","committed","ok","active",False,True),m.target_response("r","receipt","unknown","missing","unknown",False,False))

    def test_admission_not_historical_absence(self):
        with self.assertRaises(ValueError):
            m.target_response("r","receipt","absent","unknown","unknown",True,True,"fresh_unseen")
        value=m.target_response("r","receipt","absent","unknown","unknown",True,True,"durable_cancel")
        value["target"]["negative_basis"]="fresh_unseen";value["outcome"]="ok";value["error_code"]=None;value["next_action"]="authorize_first_apply"
        with self.assertRaises(ValueError):m.validate_envelope(value)

    def test_schema_and_semantics_reject_impossible(self):
        good=m.target_response("r","mutation","committed","ok","active",True,True)
        for path,val in [("scope","read"),("outcome","unknown"),("next_action","authorize_first_apply"),("extra",True)]:
            bad=copy.deepcopy(good);bad[path]=val
            with self.assertRaises(ValueError):m.validate_envelope(bad)
        bad=copy.deepcopy(good);bad["target"]["negative_basis"]="durable_cancel"
        with self.assertRaises(ValueError):m.validate_envelope(bad)
        bad=copy.deepcopy(good);bad["target"]["content"]="secret"
        with self.assertRaises(ValueError):m.validate_envelope(bad)
        with self.assertRaises(ValueError):m.target_response("r","receipt","committed","ok","active",1,True)

if __name__ == "__main__":unittest.main()
