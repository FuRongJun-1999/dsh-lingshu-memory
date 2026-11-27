import unittest
from unittest.mock import Mock
from framework.context_recall import RecallBlocked, select_evidence, revalidate_evidence


class IndependentRecallTests(unittest.TestCase):
    def setUp(self):
        self.req = dict(key='k', architecture='a', version='v1', conditions={'region':'east'})
        self.task = dict(query='fixture', requirements=[self.req], budget={'retries':1})
        self.row = dict(self.req, locator={'id':'fixture', 'revision':1, 'content_sha':'1'*64}, body='synthetic fixture')

    def test_text_and_confirmation_are_separate_real_port_calls(self):
        order = []
        def search(query, **kw):
            order.append((query, kw))
            return [self.row['locator']]
        def get(locator):
            order.append(locator)
            return dict(self.row)
        found = select_evidence(self.task, search=search, get=get, refetch=lambda:order.append('refetch'))
        records = revalidate_evidence(self.task, found, get=get)
        loc = self.row['locator']
        self.assertEqual(order, [('fixture',dict(evidence_key=None,limit=4)), loc, 'refetch',
                                 ('fixture',dict(evidence_key='k',limit=64)), loc, loc])
        self.assertEqual(records, [dict(body=self.row['body'],citation=loc)])

    def test_cap_or_version_divergence_cannot_yield_a_partial_result(self):
        get = Mock(return_value=self.row)
        with self.assertRaisesRegex(RecallBlocked, 'CANDIDATE_LIMIT'):
            select_evidence(self.task, search=Mock(side_effect=[[],[self.row['locator']]*64]),
                            get=get, refetch=lambda:None)
        get.assert_not_called()
        with self.assertRaisesRegex(RecallBlocked, 'EVIDENCE_CHANGED'):
            revalidate_evidence(self.task,[self.row],get=Mock(return_value=dict(self.row,version='v2')))
        with self.assertRaisesRegex(RecallBlocked, 'EVIDENCE_GAP'):
            revalidate_evidence(self.task,[],get=get)
