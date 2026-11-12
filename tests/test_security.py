import copy
import unittest
from framework import security as s

def binding():
 return {"context":{"tenant":"a","principal":"p","clearance":2,"auth_epoch":4,"policy_generation":7,"expires_at":200},"snapshot":{"id":"snap","content_generation":5,"policy_generation":7,"expires_at":150},"read_kind":"Read.search","query_sha":"a"*64,"response_sha":"b"*64,"cursor_sha":"c"*64}
def retention(kind="body"):
 return dict(kind=kind,lifecycle="tombstoned",deadline=100,authorized=True,legal_hold=False,commit_resolved=True,terminal_durable=True,dependencies_closed=True,audit_closed=True)

class SecurityTests(unittest.TestCase):
 def test_binding_positive_and_expiry(self):
    b=binding();self.assertTrue(s.emit_allowed(b,b,149,True,True,True));self.assertFalse(s.emit_allowed(b,b,150,True,True,True))
    b["snapshot"]["expires_at"]=300
    self.assertFalse(s.emit_allowed(b,b,200,True,True,True))
    for v in (True,-1,9007199254740992):self.assertFalse(s.emit_allowed(b,b,v,True,True,True))

 def test_all_context_bindings(self):
    for key,val in [("tenant","b"),("principal","q"),("clearance",1),("auth_epoch",5),("expires_at",201)]:
      old=binding();current=copy.deepcopy(old);current["context"][key]=val
      self.assertFalse(s.emit_allowed(old,current,100,True,True,True),key)
    old=binding();current=copy.deepcopy(old);current["context"]["policy_generation"]=8;current["snapshot"]["policy_generation"]=8
    self.assertFalse(s.emit_allowed(old,current,100,True,True,True))

 def test_actual_page_and_snapshot_bindings(self):
    for key,val in [("read_kind","Read.expand"),("query_sha","d"*64),("response_sha","d"*64),("cursor_sha","d"*64),("cursor_sha",None)]:
      old=binding();cur=copy.deepcopy(old);cur[key]=val
      self.assertFalse(s.emit_allowed(old,cur,100,True,True,True),key)
    for key,val in [("id","other"),("content_generation",6),("expires_at",151)]:
      old=binding();cur=copy.deepcopy(old);cur["snapshot"][key]=val
      self.assertFalse(s.emit_allowed(old,cur,100,True,True,True),key)

 def test_auth_and_cursor_before_emit(self):
    b=binding()
    for flags in [(False,True,True),(True,False,True),(True,True,False),(1,True,True),(True,None,True)]:self.assertFalse(s.emit_allowed(b,b,100,*flags))
    for key,val in [("clearance",True),("auth_epoch",-1),("extra","admin")]:
      c=copy.deepcopy(b["context"]);c[key]=val
      with self.assertRaises(ValueError):s.context_shape(c)
    b["snapshot"]["policy_generation"]=8
    with self.assertRaises(ValueError):s.binding_shape(b)

 def test_shape_is_not_authentication(self):
    b=binding();self.assertEqual(s.binding_shape(b),b);self.assertFalse(s.emit_allowed(b,b,100,False,True,True))
    clone=s.binding_shape(b);clone["context"]["tenant"]="changed";self.assertNotEqual(b,clone)
    b["read_kind"]="Read.get"
    with self.assertRaises(ValueError):s.binding_shape(b)

 def test_retention_positive_and_deadline(self):
    for kind in ("body","backup","intent","audit"):
      e=retention(kind);self.assertEqual(s.retention_plan(e,100),"eligible_purge");self.assertEqual(s.retention_plan(e,99),"retain")
    self.assertEqual(s.retention_plan(retention("index"),0),"eligible_rebuild_discard")
    self.assertEqual(s.retention_plan(retention("token_final"),1000),"retain")

 def test_active_quarantine_and_hold_retain(self):
    for kind in ("body","backup","intent","audit"):
      for state in ("active","quarantined"):
        e=retention(kind);e["lifecycle"]=state;self.assertEqual(s.retention_plan(e,100),"retain")
    for kind in s.KINDS:
      for key,val in [("legal_hold",True),("legal_hold",None),("authorized",False),("authorized",None)]:
        e=retention(kind);e[key]=val;self.assertEqual(s.retention_plan(e,100),"retain")

 def test_missing_recovery_evidence_retains(self):
    for kind in ("body","backup","intent","audit"):
      for key,val in [("commit_resolved",False),("terminal_durable",False),("dependencies_closed",False),("dependencies_closed",None),("deadline",None)]:
        e=retention(kind);e[key]=val;self.assertEqual(s.retention_plan(e,100),"retain",(kind,key))
    for val in (False,None):
      e=retention("audit");e["audit_closed"]=val;self.assertEqual(s.retention_plan(e,100),"retain")

 def test_binding_malformed_is_false_not_granted(self):
    for key,val in [("query_sha","A"*64),("response_sha","short"),("cursor_sha",[]),("extra",True)]:
      b=binding();b[key]=val;self.assertFalse(s.emit_allowed(b,b,100,True,True,True))
    b=binding();b["context"]["principal"]="\ud800"
    self.assertFalse(s.emit_allowed(b,b,100,True,True,True))

 def test_unknown_terminal_and_resolution_retain(self):
    for kind in ("body","backup","intent","audit"):
      for key in ("terminal_durable","commit_resolved"):
        e=retention(kind);e[key]=None;self.assertEqual(s.retention_plan(e,100),"retain")

 def test_retention_strict_shape(self):
    for key,val in [("authorized",1),("deadline",True),("kind","mystery"),("lifecycle","deleted"),("extra",True)]:
      e=retention();e[key]=val
      with self.assertRaises(ValueError):s.retention_plan(e,100)
    e=retention();del e["legal_hold"]
    with self.assertRaises(ValueError):s.retention_plan(e,100)

if __name__=="__main__":unittest.main()
