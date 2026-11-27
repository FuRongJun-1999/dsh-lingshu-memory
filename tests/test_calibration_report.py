import inspect
import unittest
from unittest.mock import Mock
from framework import calibration_report as mod
from framework.spec import digest
from test_shadow_runtime import ctx


def frame(pos=1,neg=3):
    return dict(policy_generation=1,samples=[dict(confidence_bp=6000,positive=pos,negative=neg)])


def call(row,**kw):
    args=dict(expected_sha=digest(row),context=ctx(),now=10,allowed=lambda _:True,snapshot=lambda _:row)
    return mod.calibration_report(**(args | kw))


class CalibrationTests(unittest.TestCase):
    def test_exact_gap_and_insufficient_evidence(self):
        self.assertEqual(call(frame()),dict(samples=1,positive=1,negative=3,expected=[3,5],actual=[1,4],
                                           gap=[7,20],verdict='overconfident'))
        self.assertEqual(call(frame(0,2))['verdict'],'insufficient_data')
        empty=call(dict(policy_generation=1,samples=[]))
        self.assertEqual((empty['gap'],empty['verdict']),(None,'insufficient_data'))

    def test_scope_and_policy_before_report(self):
        reader=Mock()
        self.assertEqual(call(frame(),allowed=lambda _:False,snapshot=reader),{'error':'NOT_FOUND_OR_DENIED'})
        reader.assert_not_called()
        self.assertEqual(call(dict(frame(),policy_generation=2)),{'error':'POLICY_CHANGED'})
        bad=frame();bad['samples'][0]['confidence_bp']=10001
        self.assertEqual(call(bad),{'error':'CALIBRATION_INVALID'})

    def test_changed_sample_and_digest_mutant(self):
        row=frame();old=digest(row);row['samples'][0]['negative']=8
        self.assertEqual(call(row,expected_sha=old),{'error':'CALIBRATION_CHANGED'})
        src=inspect.getsource(mod);needle="if digest(dict(policy_generation=actor['policy_generation'],samples=rows))!=expected_sha:"
        self.assertEqual(src.count(needle),1);ns={}
        exec(compile(src.replace(needle,'if False:',1),'<calibration-digest-mutant>','exec'),ns)
        self.assertEqual(ns['calibration_report'](expected_sha=old,context=ctx(),now=10,
                         allowed=lambda _:True,snapshot=lambda _:row)['negative'],8)
