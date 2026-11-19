"""Isolated delivery boundary. A validated memory response can produce only data frames.

The consumer and its control capability are trusted Python objects, not wire fields.
This module does not authenticate a response, call a model, parse commands or run tools.
"""
from dataclasses import dataclass
from framework.contracts import validate_full_response


@dataclass(frozen=True)
class MemoryFrame:
    node_id: str
    revision: int
    content_sha: str
    body: str


def memory_frames(response):
    """Validate the entire read before delivering anything; never parse or flatten body text."""
    result = validate_full_response(response)
    if result['scope'] != 'read' or result['outcome'] != 'ok' or not isinstance(result['records'], list):
        raise ValueError('SUCCESSFUL_RECORD_READ_REQUIRED')
    return tuple(MemoryFrame(r['locator']['id'], r['locator']['revision'], r['locator']['content_sha'], r['body'])
                 for r in result['records'])


class FixtureReceiver:
    """Observable in-memory endpoint. The only control action is incrementing a counter."""
    def __init__(self, *, control_capability):
        if type(control_capability) is not object:
            raise ValueError('OPAQUE_CAPABILITY_REQUIRED')
        self._cap = control_capability
        self.data = []
        self.control_count = 0

    def receive_memory(self, response):
        self.data.extend(memory_frames(response))

    def observe_control(self, capability):
        if capability is not self._cap:
            raise ValueError('CONTROL_CAPABILITY_REQUIRED')
        self.control_count += 1
