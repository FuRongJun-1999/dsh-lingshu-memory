import hashlib
import inspect
import unittest
from unittest.mock import Mock, patch

from framework import python_declarations, source_snapshot
from framework.source_ref import read_source_ref
from test_shadow_runtime import ctx


def args(raw, **kw):
    return dict(dict(source_id='fixture.py',expected_sha=hashlib.sha256(raw).hexdigest(),context=ctx(),now=10,
                     authorize=lambda *_:True,snapshot=lambda *_:raw),**kw)


class PythonDeclarationsTests(unittest.TestCase):
    def test_exact_declarations_without_execution_or_decorator(self):
        first='async def 取用():\r\n    return 1\r\n'.encode()
        second=b'class Example:\n    def member(self):\n        return 2'
        raw=b'raise RuntimeError("must not execute")\r\n@missing_decorator\r\n'+first+b'\r\n'+second
        kw=args(raw); result=python_declarations.index_python(**kw)['declarations']
        self.assertEqual([(x['name'],x['kind'],x['locator']['start'],x['locator']['end']) for x in result],
                         [('取用','async_function',3,4),('Example','class',6,8)])
        for item, region in zip(result,(first,second)):
            got=read_source_ref(item['locator'],**{k:kw[k] for k in ('context','now','authorize','snapshot')})
            self.assertEqual(got['text'].encode('utf-8'),region)

    def test_authorization_precedes_read_and_malformed_sources_fail(self):
        run=python_declarations.index_python
        port=Mock(return_value=b'def f(): pass')
        self.assertEqual(run(**args(b'',authorize=lambda *_:False,snapshot=port)),{'error':'NOT_FOUND_OR_DENIED'})
        port.assert_not_called()
        self.assertEqual(run(**args(b'',snapshot=port)),{'error':'SOURCE_CHANGED'})
        self.assertEqual(run(**args(b'def x(\n')),{'error':'INVALID_PYTHON'})
        self.assertEqual(run(**args(b'def f():\r    pass')),{'error':'UNSUPPORTED_NEWLINES'})
        self.assertEqual(run(**args(b'def f(): pass\n'*65)),{'error':'DECLARATION_BUDGET'})

    def test_mutation_exposes_candidate_from_changed_version(self):
        raw=b'def fn(): pass\n'; kw=args(raw,expected_sha='1'*64)
        self.assertEqual(python_declarations.index_python(**kw),{'error':'SOURCE_CHANGED'})
        src=inspect.getsource(source_snapshot); guard='if hashlib.sha256(raw).hexdigest() != expected_sha:'
        self.assertEqual(src.count(guard),1)
        changed={};exec(compile(src.replace(guard,'if False:',1),'<python-source-version-mutant>','exec'),changed)
        with patch.object(python_declarations,'authorized_source',changed['authorized_source']):
            self.assertEqual(python_declarations.index_python(**kw)['declarations'][0]['name'],'fn')
