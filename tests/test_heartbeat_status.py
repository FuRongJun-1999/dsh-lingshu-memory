import inspect
import unittest
from unittest.mock import Mock
from framework import heartbeat_status as mod
from test_shadow_runtime import ctx

ROW=dict(service='fixture',generation=4,policy_generation=1,observed_at=10,busy=True)


def options(**kw):
    return dict(dict(service='fixture',generation=4,ttl=20,context=ctx(),now=29,
                     allowed=lambda *_:True,snapshot=lambda *_:dict(ROW)),**kw)


class HeartbeatStatusTests(unittest.TestCase):
    def test_interval_and_no_old_busy_flag(self):
        self.assertEqual(mod.heartbeat_status(**options()),dict(status='fresh',age=19,reported_busy=True))
        self.assertEqual(mod.heartbeat_status(**options(now=30)),{'status':'stale'})
        self.assertEqual(mod.heartbeat_status(**options(now=9)),{'error':'HEARTBEAT_FUTURE'})
        self.assertEqual(mod.heartbeat_status(**options(snapshot=lambda *_:None)),{'status':'unknown'})

    def test_denial_and_invalid_record(self):
        port=Mock()
        self.assertEqual(mod.heartbeat_status(**options(allowed=lambda *_:False,snapshot=port)),{'error':'HEARTBEAT_DENIED'})
        self.assertEqual(mod.heartbeat_status(**options(now=1000,snapshot=port)),{'error':'AUTH_REQUIRED'})
        port.assert_not_called()
        self.assertEqual(mod.heartbeat_status(**options(snapshot=lambda *_:dict(ROW,service='foreign'))),{'error':'HEARTBEAT_INVALID'})

    def test_generation_or_policy_mismatch_and_boundary_mutant(self):
        self.assertEqual(mod.heartbeat_status(**options(generation=5)),{'error':'HEARTBEAT_CHANGED'})
        self.assertEqual(mod.heartbeat_status(**options(snapshot=lambda *_:dict(ROW,policy_generation=2))),{'error':'HEARTBEAT_CHANGED'})
        src=inspect.getsource(mod);self.assertEqual(src.count('if age>=ttl:'),1);n={}
        exec(compile(src.replace('if age>=ttl:','if age>ttl:',1),'<heartbeat-boundary-mutant>','exec'),n)
        self.assertEqual(n['heartbeat_status'](**options(now=30))['status'],'fresh')
