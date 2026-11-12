import copy
import unittest
from framework import migration as m

U={"state":"unknown"};INF={"state":"unbounded"}
def at(v):return {"state":"instant","value":v}
A="2024-01-01T00:00:00Z";B="2024-01-01T00:00:01Z"
def axes(start=U,end=U):return {"observed":{"start":copy.deepcopy(INF),"end":copy.deepcopy(INF)},"effective":{"start":copy.deepcopy(start),"end":copy.deepcopy(end)}}

class MigrationTests(unittest.TestCase):
 def test_inventory_exact_coverage(self):
    rows=m.load_inventory()["operations"]
    self.assertEqual(len(rows),44);self.assertEqual(sum(x["tool"]=="cg" for x in rows),39)
    self.assertFalse(any(x["runtime_ready"] for x in rows))
    self.assertEqual(m.operation_plan("cg","write"),{"decision":"specification_only","target":"Write","runtime_ready":False})
    self.assertEqual(m.operation_plan("stg","state_chain")["target"],"extension")
    for op in ("READ"," read","", "magic"):
      self.assertEqual(m.operation_plan("cg",op)["decision"],"reject")
    self.assertEqual(m.operation_plan("lingshu_cg","read")["decision"],"reject")

 def test_inventory_rejects_source_and_mapping_drift(self):
    from unittest.mock import patch
    original=m.load_inventory()
    for field,val in [("upstream_commit","0"*40),("source_sha256","0"*64),("default","allow")]:
      bad=copy.deepcopy(original);bad[field]=val
      with patch.object(m,"parse",return_value=bad):
        with self.assertRaises(ValueError):m.load_inventory()
    bad=copy.deepcopy(original);next(x for x in bad["operations"] if x["op"]=="verify")["target"]="Govern"
    with patch.object(m,"parse",return_value=bad):
      with self.assertRaises(ValueError):m.load_inventory()
    text=(m.ROOT/"docs/COMPATIBILITY.md").read_text(encoding="utf-8")
    for x in original["operations"]:
      self.assertIn('| '+x['tool']+' | '+x['op']+' | '+x['target']+' | '+str(x['source_line'])+' |',text)

 def test_empty_profiles_do_not_grant_shadow(self):
    for a,b in [([],[]),([],['cas']),(['acl'],[])]:
      with self.assertRaises(ValueError):m.downgrade(a,b,{})

 def test_downgrade_matrix(self):
    read=["acl","conditions","source_revision"];write=["token_history","cas"]
    full={x:True for x in read+write}
    self.assertEqual(m.downgrade(read,write,full),"eligible_isolated_shadow")
    for x in read:
      v=full|{x:False};self.assertEqual(m.downgrade(read,write,v),"reject")
      v=full|{x:None};self.assertEqual(m.downgrade(read,write,v),"defer")
    for x in write:
      self.assertEqual(m.downgrade(read,write,full|{x:False}),"read_only")
      self.assertEqual(m.downgrade(read,write,full|{x:None}),"defer")
    self.assertEqual(m.downgrade(read,write,{}),"defer")
    for bad in ({"acl":1},{1:True},{"acl":"yes"}):
      with self.assertRaises(ValueError):m.downgrade(read,write,bad)

 def test_legacy_bytes_not_silently_transformed(self):
    for raw in (b"abc\r\n",b"\xff\x00",'未知条件 1.000 2024-01-01T00:00:00.5Z'.encode()):
      c=m.legacy_capsule(raw);self.assertEqual(m.restore_capsule(c),raw);self.assertEqual(c["interpretation"],"DEFER")
    self.assertEqual(m.legacy_capsule(b"\xff")["encoding"],"opaque_bytes")
    c=m.legacy_capsule(b"x");c["sha256"]="0"*64
    with self.assertRaises(ValueError):m.restore_capsule(c)
    for x in ("abc",b"x"*131073):
      with self.assertRaises(ValueError):m.legacy_capsule(x)

 def test_strict_time_precision(self):
    self.assertEqual(m.instant("2024-02-29T00:00:00Z").day,29)
    for x in (A.replace('Z','+00:00'),"2024-02-30T00:00:00Z","2024-01-01", "2024-01-01T00:00:00.5Z",True,1704067200,"2024-01-01T00:00:60Z"):
      with self.assertRaises(ValueError):m.instant(x)

 def test_half_open_and_empty(self):
    x=axes(at(A),at(B));self.assertEqual(m.time_match(x,"effective",A),"MATCH");self.assertEqual(m.time_match(x,"effective",B),"NO_MATCH")
    self.assertEqual(m.time_match(axes(at(A),at(A)),"effective",A),"NO_MATCH")
    with self.assertRaises(ValueError):m.time_bundle(axes(at(B),at(A)))

 def test_unknown_not_unbounded(self):
    self.assertEqual(m.time_match(axes(),"effective",A),"DEFER")
    self.assertEqual(m.time_match(axes(),"observed",A),"MATCH")
    self.assertEqual(m.time_match(axes(U,at(A)),"effective",A),"NO_MATCH")
    self.assertEqual(m.time_match(axes(at(B),U),"effective",A),"NO_MATCH")
    self.assertEqual(m.time_match(axes(U,at(B)),"effective",A),"DEFER")
    with self.assertRaises(ValueError):m.time_match(axes(),"automatic",A)
    with self.assertRaises(ValueError):m.time_bundle({"observed":axes()["observed"]})
    with self.assertRaises(ValueError):m.bound({"state":"unknown","value":A})

 def test_capsule_metadata_and_encoding_tampering_rejected(self):
    for field,val in [("encoding","opaque_bytes"),("interpretation","ACCEPT"),("raw_base64","@@@"),("raw_base64","eA==\n")]:
      x=m.legacy_capsule(b"x");x[field]=val
      with self.assertRaises(ValueError):m.restore_capsule(x)

 def test_inventory_duplicate_and_ready_rejected(self):
    from unittest.mock import patch
    src=m.load_inventory()
    for change in ("duplicate","ready"):
      bad=copy.deepcopy(src)
      if change=="duplicate":bad["operations"][1]=copy.deepcopy(bad["operations"][0])
      else:bad["operations"][0]["runtime_ready"]=True
      with patch.object(m,"parse",return_value=bad):
        with self.assertRaises(ValueError):m.load_inventory()

 def test_conditions_preserve_not_execute(self):
    x={"carrier":{"state":"declared","text":"tenant=public"},"method":{"state":"declared","text":"__import__('os')"},"existence":{"state":"unknown"}}
    y=m.condition_bundle(x);self.assertEqual(x,y);self.assertIsNot(x,y);y["method"]["text"]="changed";self.assertNotEqual(x,y)
    for v in ({},x|{"role":"admin"},x|{"existence":{"state":"unknown","text":"true"}},x|{"carrier":{"state":"declared","text":""}}):
      with self.assertRaises(ValueError):m.condition_bundle(v)

if __name__ == "__main__":unittest.main()
