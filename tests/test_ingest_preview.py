import hashlib
import inspect
import unittest
from unittest.mock import Mock
from framework import ingest_preview as mod
from test_shadow_runtime import ctx


ROW=b'{"source":"fixture","seq":2,"text":"fixture body"}\n'


def call(raw=ROW, **kw):
    opts=dict(source_id='fixture',expected_sha=hashlib.sha256(raw).hexdigest(),watermark=1,limit=2,
              context=ctx(),now=10,allowed=lambda *_:True,snapshot=lambda *_:raw)
    return mod.preview_ingest(**(opts | kw))


class IngestPreviewTests(unittest.TestCase):
    def test_pending_only_and_watermark_unchanged(self):
        self.assertEqual(call(),dict(source='fixture',watermark=1,pending=1,applied=False))
        self.assertEqual(call(watermark=2)['pending'],0)
        self.assertEqual(call(ROW+ROW.replace(b':2',b':3'),limit=1),{'error':'INGEST_EVENT_BUDGET'})

    def test_denial_and_changed_source(self):
        port=Mock()
        self.assertEqual(call(allowed=lambda *_:False,snapshot=port),{'error':'NOT_FOUND_OR_DENIED'})
        port.assert_not_called()
        self.assertEqual(call(expected_sha='0'*64),{'error':'SOURCE_CHANGED'})

    def test_invalid_tail_fails_even_below_watermark(self):
        self.assertEqual(call(ROW+ROW,watermark=9),{'error':'INGEST_EVENT_INVALID'})
        self.assertEqual(call(ROW.replace(b'"seq":2',b'"seq":1,"seq":2')),{'error':'INGEST_EVENT_INVALID'})
        self.assertEqual(call(ROW*257),{'error':'INGEST_SCAN_BUDGET'})
        raw=ROW.replace(b'fixture"',b'foreign"')
        self.assertEqual(call(raw),{'error':'INGEST_EVENT_INVALID'})
        code=inspect.getsource(mod);needle=" or item['source']!=source_id";ns={}
        self.assertEqual(code.count(needle),1)
        exec(compile(code.replace(needle,'',1),'<ingest-scope-mutant>','exec'),ns)
        self.assertEqual(ns['preview_ingest'](source_id='fixture',expected_sha=hashlib.sha256(raw).hexdigest(),
                         watermark=1,limit=2,context=ctx(),now=10,allowed=lambda *_:True,snapshot=lambda *_:raw)['pending'],1)
