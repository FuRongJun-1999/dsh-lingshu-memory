import hashlib
import inspect
import unittest
from unittest.mock import Mock, patch
from framework import source_ref as module, source_snapshot
from test_shadow_runtime import ctx


def sha(value):return hashlib.sha256(value).hexdigest()


class SourceRefTests(unittest.TestCase):
    def test_raw_region_boundaries_with_unicode_and_crlf(self):
        source='甲\r\n乙\n最后'.encode()
        expected='甲\r\n乙\n'.encode()
        ref=dict(source_id='fixture.doc',source_sha=sha(source),start=1,end=2,region_sha=sha(expected))
        port=Mock(return_value=source)
        kw=dict(context=ctx(),now=10,authorize=lambda *_:True,snapshot=port)
        self.assertEqual(module.read_source_ref(ref,**kw),dict(locator=ref,text=expected.decode(),trust='untrusted_source'))
        last='最后'.encode();tail=dict(ref,start=3,end=3,region_sha=sha(last))
        self.assertEqual(module.read_source_ref(tail,**kw)['text'],last.decode())
        self.assertEqual(module.read_source_ref(dict(ref,end=4),**kw),{'error':'REGION_NOT_FOUND'})

    def test_permission_before_read_and_no_path_surface(self):
        port=Mock(return_value=None); ref=dict(source_id='fixture.doc',source_sha='1'*64,start=1,end=1,region_sha='2'*64)
        kw=dict(context=ctx(),now=10,authorize=lambda *_:False,snapshot=port)
        self.assertEqual(module.read_source_ref(ref,**kw),{'error':'NOT_FOUND_OR_DENIED'})
        self.assertEqual(module.read_source_ref(ref,**dict(kw,now=1000)),{'error':'AUTH_REQUIRED'})
        with self.assertRaisesRegex(ValueError,'INVALID_SOURCE_REFERENCE'):
            module.read_source_ref(dict(ref,path='fixture'),**kw)
        port.assert_not_called()
        self.assertEqual(module.read_source_ref(ref,**dict(kw,authorize=lambda *_:True)),{'error':'NOT_FOUND_OR_DENIED'})

    def test_source_and_region_drift_fail_without_text_and_mutant_is_detected(self):
        original=b'fixture\nsecond\n'; updated=b'fixture\nchanged\n'
        ref=dict(source_id='fixture.doc',source_sha=sha(original),start=1,end=1,region_sha=sha(b'fixture\n'))
        kw=dict(context=ctx(),now=10,authorize=lambda *_:True,snapshot=lambda *_:updated)
        self.assertEqual(module.read_source_ref(ref,**kw),{'error':'SOURCE_CHANGED'})
        text=inspect.getsource(source_snapshot);guard="if hashlib.sha256(raw).hexdigest() != expected_sha:"
        self.assertEqual(text.count(guard),1)
        mutant={};exec(compile(text.replace(guard,'if False:',1),'<ref-version-mutant>','exec'),mutant)
        with patch.object(module,'authorized_source',mutant['authorized_source']):
            self.assertEqual(module.read_source_ref(ref,**kw)['text'],'fixture\n')
        wrong=dict(ref,source_sha=sha(updated),region_sha='0'*64)
        self.assertEqual(module.read_source_ref(wrong,**kw),{'error':'REGION_CHANGED'})
