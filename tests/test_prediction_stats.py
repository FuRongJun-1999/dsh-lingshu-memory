import inspect
import unittest
from unittest.mock import Mock
from framework import prediction_stats as mod
from framework.spec import digest
from test_shadow_runtime import ctx


def frame():
    return dict(policy_generation=1,feedback=[dict(prediction='a',hit=True),dict(prediction='b',hit=False)])


def args(row=None,**kw):
    f=frame() if row is None else row
    return dict(dict(expected_sha=digest(f),context=ctx(),now=10,allowed=lambda _:True,snapshot=lambda _:f),**kw)


class PredictionStatsTests(unittest.TestCase):
    def test_exact_rate_and_no_fallback_for_empty_sample(self):
        self.assertEqual(mod.prediction_stats(**args()),dict(status='measured',feedback_samples=2,hits=1,hit_rate=[1,2]))
        self.assertEqual(mod.prediction_stats(**args(dict(policy_generation=1,feedback=[]))),
                         dict(status='insufficient',feedback_samples=0,hits=0,hit_rate=None))

    def test_denial_precedes_read_policy_and_label_checks(self):
        port=Mock()
        self.assertEqual(mod.prediction_stats(**args(allowed=lambda _:False,snapshot=port)),{'error':'FEEDBACK_DENIED'})
        self.assertEqual(mod.prediction_stats(**args(now=1000,snapshot=port)),{'error':'AUTH_REQUIRED'})
        port.assert_not_called()
        self.assertEqual(mod.prediction_stats(**args(dict(frame(),policy_generation=2))),{'error':'POLICY_CHANGED'})
        row=frame();row['feedback'][1]['hit']=1
        self.assertEqual(mod.prediction_stats(**args(row)),{'error':'FEEDBACK_INVALID'})
        row=frame();row['feedback'][1]['prediction']='a'
        self.assertEqual(mod.prediction_stats(**args(row)),{'error':'FEEDBACK_INVALID'})

    def test_version_check_prevents_feedback_replacement(self):
        row=frame(); kw=args(row);row['feedback'][1]['hit']=True
        self.assertEqual(mod.prediction_stats(**kw),{'error':'FEEDBACK_CHANGED'})
        code=inspect.getsource(mod);needle="if digest(dict(policy_generation=actor['policy_generation'],feedback=rows))!=expected_sha:";ns={}
        self.assertEqual(code.count(needle),1)
        exec(compile(code.replace(needle,'if False:',1),'<prediction-feedback-mutant>','exec'),ns)
        self.assertEqual(ns['prediction_stats'](**kw)['hit_rate'],[1,1])
