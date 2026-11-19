"""Each fault must change one observation, not merely crash the test runner."""
import importlib.util
import pathlib
import tempfile
import unittest

from framework.spec import ROOT
from sandbox_runtime import source_boundary as original
from test_contracts_v2 import ok_read_resp


def observations(module):
    cap = object()
    receiver = module.FixtureReceiver(control_capability=cap)
    receiver.observe_control(cap)
    before = receiver.control_count
    good = ok_read_resp()
    receiver.receive_memory(good)
    delivery = tuple(frame.body for frame in receiver.data)
    after = receiver.control_count
    corrupt = ok_read_resp()
    corrupt['records'][0]['body_sha'] = '0' * 64
    try:
        receiver.receive_memory(corrupt)
    except ValueError:
        rejected = True
    else:
        rejected = False
    return {'control_observed': before == 1, 'data_delivered': delivery == ('hello world',),
            'separate_channels': after == before, 'bad_digest_rejected': rejected}


class SourceBoundaryMutationTests(unittest.TestCase):
    def test_four_single_faults_change_only_the_expected_observation(self):
        text = (ROOT / 'sandbox_runtime/source_boundary.py').read_text(encoding='utf-8')
        reference = observations(original)
        self.assertEqual(reference, dict(control_observed=True, data_delivered=True,
                                         separate_channels=True, bad_digest_rejected=True))
        anchor = 'self.data.extend(memory_frames(response))'
        faults = [
            ('control_observed', 'self.control_count += 1', 'self.control_count += 0'),
            ('data_delivered', anchor, 'memory_frames(response)'),
            ('separate_channels', anchor, anchor + '\n        self.control_count += 1'),
            ('bad_digest_rejected', 'result = validate_full_response(response)', 'result = response'),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for index, (check, old, new) in enumerate(faults):
                with self.subTest(check=check):
                    self.assertEqual(text.count(old), 1)
                    path = pathlib.Path(tmp) / ('receiver%d.py' % index)
                    path.write_text(text.replace(old, new, 1), encoding='utf-8')
                    spec = importlib.util.spec_from_file_location(path.stem, path)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    self.assertEqual(observations(mod), dict(reference, **{check: False}))
