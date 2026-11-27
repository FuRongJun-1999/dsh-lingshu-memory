import inspect
import unittest
from unittest.mock import Mock
from framework import insight_rate as mod
from framework.spec import digest
from test_shadow_runtime import ctx


def frame():
    return dict(policy_generation=1,events=[dict(id='a',recorded_at=5,state='verified'),
            dict(id='b',recorded_at=6,state='falsified'),dict(id='c',recorded_at=7,state='pending'),
            dict(id='d',recorded_at=4,state='falsified')])


def options(**kw):
    return dict(dict(expected_sha=digest(frame()),since=5,minimum=2,context=ctx(),now=10,
                    allowed=lambda _:True,snapshot=lambda _:frame()),**kw)


class InsightRateTests(unittest.TestCase):
    def test_boundary_pending_and_no_small_sample_claim(self):
        self.assertEqual(mod.insight_rate(**options()),dict(verified=1,falsified=1,pending=1,decided=2,
                         status='measured',rate=[1,2]))
        self.assertEqual(mod.insight_rate(**options(minimum=3))['rate'],None)
        self.assertEqual(mod.insight_rate(**options(since=7))['decided'],0)

    def test_denial_before_snapshot_and_policy(self):
        read=Mock()
        self.assertEqual(mod.insight_rate(**options(allowed=lambda _:False,snapshot=read)),{'error':'INSIGHT_DENIED'})
        read.assert_not_called()
        self.assertEqual(mod.insight_rate(**options(snapshot=lambda _:dict(frame(),policy_generation=2))),{'error':'POLICY_CHANGED'})

    def test_drift_outside_window_still_rejected(self):
        row=frame(); row['events'][-1]['state']='verified';kw=options(snapshot=lambda _:row)
        self.assertEqual(mod.insight_rate(**kw),{'error':'INSIGHT_CHANGED'})
        src=inspect.getsource(mod); guard="if digest(dict(policy_generation=actor['policy_generation'],events=rows))!=expected_sha:";ns={}
        self.assertEqual(src.count(guard),1)
        exec(compile(src.replace(guard,'if False:',1),'<insight-digest-mutant>','exec'),ns)
        self.assertEqual(ns['insight_rate'](**kw)['status'],'measured')
        row['events'].append(row['events'][0]); self.assertEqual(mod.insight_rate(**kw),{'error':'INSIGHT_INVALID'})
