import copy
import hashlib
import unittest
from sandbox_runtime.store import SyntheticStore, Probe


def context(**kwargs):
    c=dict(tenant="a",principal="p",clearance=2,auth_epoch=1,policy_generation=1,expires_at=100)
    c.update(kwargs);return c


def record(name="target", **kwargs):
    r=dict(id=name,revision=1,tenant="a",sensitivity=1,creation_readers=["p"],current_readers=["p"],edges=[],tombstoned=False,body="blue widget limit 8",key="widget.limit",architecture="widget",version="v1",conditions={"region":"east"})
    r.update(kwargs);return r


class SyntheticStoreTests(unittest.TestCase):
    def test_actual_search_read_bytes_and_observer(self):
        p=Probe();s=SyntheticStore([record()],synthetic=True,probe=p)
        hits=s.search("blue widget",context(),1)
        self.assertEqual(hits,[dict(id="target",revision=1,content_sha=hashlib.sha256(b"blue widget limit 8").hexdigest())])
        self.assertEqual(s.get(hits[0],context(),1)["body"],"blue widget limit 8")
        self.assertEqual(p.events,[dict(operation="search",returned=1,mode="text"),dict(operation="get",matched=True,bytes=19)])

    def test_exact_key_locates_under_noise(self):
        rows=[record("noise%04d"%i,key="other.%d"%i,body="blue widget limit irrelevant") for i in range(500)]+[record()]
        p=Probe();s=SyntheticStore(rows,synthetic=True,probe=p)
        self.assertEqual(s.search("widget",context(),1,evidence_key="widget.limit",limit=1)[0]["id"],"target")
        self.assertEqual(s.search("missing",context(),1,evidence_key="not-present"),[])

    def test_filter_before_limit_no_ids_or_counts_for_hidden(self):
        rows=[record("aaa-hidden",current_readers=[]),record("bbb-foreign",tenant="b"),record("ccc-high",sensitivity=3),record("zzz-visible")]
        p=Probe();s=SyntheticStore(rows,synthetic=True,probe=p)
        self.assertEqual([x["id"] for x in s.search("widget",context(),1,evidence_key="widget.limit",limit=1)],["zzz-visible"])
        self.assertEqual(p.events,[dict(operation="search",returned=1,mode="key")])

    def test_derived_and_all_dangling_quarantine(self):
        root=record("root",sensitivity=3);sha=hashlib.sha256(root["body"].encode()).hexdigest()
        child=record("child",edges=[dict(target="root",relation="derived",revision=1,content_sha=sha)])
        dangling=record("dangling",edges=[dict(target="absent",relation="corroborating",revision=1,content_sha=sha)])
        s=SyntheticStore([root,child,dangling],synthetic=True,probe=Probe())
        self.assertEqual(s.search("widget",context(),1),[])

    def test_locator_mismatch_and_unauthorized_uniform_none(self):
        p=Probe();s=SyntheticStore([record()],synthetic=True,probe=p)
        hit=s.search("widget",context(),1)[0]
        for bad in [dict(hit,id="absent"),dict(hit,revision=2),dict(hit,content_sha="0"*64)]:self.assertIsNone(s.get(bad,context(),1))
        self.assertIsNone(s.get(hit,context(principal="q"),1))
        self.assertTrue(all(x==dict(operation="get",matched=False,bytes=0) for x in p.events[1:]))

    def test_explicit_isolation_and_closed_input(self):
        for flag in (False,None,1,"true"):
            with self.assertRaises(ValueError):SyntheticStore([record()],synthetic=flag,probe=Probe())
        for bad in [record(revision=True),record(sensitivity=True),record(current_readers=["q"]),record(extra=True),record(body="\ud800"),record(conditions={"region":None})]:
            with self.assertRaises(ValueError):SyntheticStore([bad],synthetic=True,probe=Probe())
        with self.assertRaises(ValueError):SyntheticStore([record(),record()],synthetic=True,probe=Probe())

    def test_fixture_and_return_are_copied(self):
        original=record();s=SyntheticStore([original],synthetic=True,probe=Probe());original["body"]="mutated"
        hits=s.search("widget",context(),1);first=s.get(hits[0],context(),1);first["body"]="mutated"
        self.assertEqual(s.get(hits[0],context(),1)["body"],"blue widget limit 8")

    def test_expiry_invalid_limits_and_no_implicit_now(self):
        s=SyntheticStore([record()],synthetic=True,probe=Probe())
        for now in (100,True,-1,9007199254740992):
            with self.assertRaises(ValueError):s.search("widget",context(),now)
        for limit in (True,0,65):
            with self.assertRaises(ValueError):s.search("widget",context(),1,limit=limit)
