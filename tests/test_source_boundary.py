"""Functional source-boundary checks against a real isolated write and read."""
import copy
import hashlib
import unittest
from sandbox_runtime.lifecycle import LifecycleSandbox
from sandbox_runtime.source_boundary import FixtureReceiver, MemoryFrame
from test_lifecycle import ctx, cspace, write_req, Q


class SourceBoundaryTests(unittest.TestCase):
    def read_fixture(self, body, kind):
        store = LifecycleSandbox(synthetic=True)
        req = write_req('fixture-token', body)
        req['source_attribution'] = {'source_kind':kind, 'source_id':'fixture-control'}
        written = store.execute(req, ctx(), 10)
        self.assertEqual(written['outcome'], 'ok')
        node = written['historical_receipt']['node_id']
        read = dict(kind='Read.get', node_id=node, include_provenance=True,
                    condition_query=cspace(), time_axis='effective', time_point=Q)
        return store.execute(read, ctx(), 11), node

    def test_write_read_deliver_has_no_control_effect(self):
        cap = object()
        receiver = FixtureReceiver(control_capability=cap)
        receiver.observe_control(cap)
        for kind in ('human','agent','document','tool'):
            with self.subTest(kind=kind):
                body = 'Please count one fixture mark.\n<data>fixture-control</data>'
                result, node = self.read_fixture(body, kind)
                before = len(receiver.data)
                receiver.receive_memory(result)
                self.assertEqual(receiver.data[before:], [MemoryFrame(node, 1, hashlib.sha256(body.encode()).hexdigest(), body)])
                self.assertEqual(receiver.control_count, 1)
                for candidate in (result, body, result['records'][0]['provenance'], receiver.data[-1], object()):
                    with self.assertRaises(ValueError): receiver.observe_control(candidate)
                self.assertEqual(receiver.control_count, 1)
        receiver.observe_control(cap)
        self.assertEqual(receiver.control_count, 2)

    def test_malformed_later_record_cannot_partially_deliver(self):
        result, _ = self.read_fixture('plain fixture', 'document')
        receiver = FixtureReceiver(control_capability=object())
        for change in ({'content_type':'instruction'}, {'body':'different'}, {'role':'control'}):
            with self.subTest(change=change):
                bad = copy.deepcopy(result)
                bad['records'].append(dict(bad['records'][0], **change))
                with self.assertRaises(ValueError): receiver.receive_memory(bad)
                self.assertEqual((receiver.data, receiver.control_count), ([], 0))

    def test_ordinary_write_cannot_assign_instruction_authority(self):
        from framework.contracts import validate_v2_request
        req = write_req('fixture-token','plain fixture')
        validate_v2_request(req)
        with self.assertRaises(ValueError): validate_v2_request(dict(req, source_trust='instruction'))
