import hashlib
import inspect
import unittest
from unittest.mock import Mock

from framework import document_sections
from framework.source_ref import read_source_ref
from test_shadow_runtime import ctx


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def params(raw, **changes):
    return dict(dict(source_id='fixture.doc',expected_sha=sha(raw),context=ctx(),now=10,
                     authorize=lambda *_:True,snapshot=lambda *_:raw),**changes)


class DocumentSectionsTests(unittest.TestCase):
    def test_generated_locators_read_back_independent_raw_sections(self):
        first='# 标题\r\n'.encode()+b'\x60\x60\x60\x60text\n## hidden\n\x60\x60\x60\n### still hidden\n\x60\x60\x60\x60\n----\n'
        second='## 结尾'.encode()
        raw=b'---\n# not a heading\n---\n'+first+second
        kw=params(raw)
        result=document_sections.index_document(**kw)['sections']
        self.assertEqual([(x['level'],x['locator']['start'],x['locator']['end']) for x in result],[(1,4,10),(2,11,11)])
        for card,expected in zip(result,(first,second)):
            out=read_source_ref(card['locator'],**{k:kw[k] for k in ('context','now','authorize','snapshot')})
            self.assertEqual(out['text'].encode(),expected)
        self.assertEqual(set(result[0]),{'level','locator'})

    def test_authorization_and_source_version_precede_parsing(self):
        raw=b'# header\n';port=Mock(return_value=raw)
        self.assertEqual(document_sections.index_document(**params(raw,authorize=lambda *_:False,snapshot=port)),{'error':'NOT_FOUND_OR_DENIED'})
        port.assert_not_called()
        wrong=params(raw,expected_sha='1'*64,snapshot=port)
        self.assertEqual(document_sections.index_document(**wrong),{'error':'SOURCE_CHANGED'})
        self.assertEqual(document_sections.index_document(**params(b'\xff')),{'error':'UNSUPPORTED_SOURCE'})
        self.assertEqual(document_sections.index_document(**params(b'# ok\n~~~\n# inside')),{'error':'UNCLOSED_FENCE'})
        self.assertEqual(document_sections.index_document(**params(b'---\n# inside')),{'error':'UNCLOSED_FRONTMATTER'})
        self.assertEqual(document_sections.index_document(**params(b'# h\n'*65)),{'error':'SECTION_BUDGET'})
        self.assertEqual(document_sections.index_document(**params(b'# h\n'+b'body\n'*256)),{'error':'SECTION_BUDGET'})

    def test_shorter_fence_mutation_creates_false_section(self):
        raw=b'# a\n~~~~\n~~~\n## inside\n~~~~\n# b'
        self.assertEqual(len(document_sections.index_document(**params(raw))['sections']),2)
        source=inspect.getsource(document_sections); guard=' and len(marker[1])>=len(fence)'
        self.assertEqual(source.count(guard),1)
        mutant={};exec(compile(source.replace(guard,'',1),'<section-fence-mutant>','exec'),mutant)
        self.assertEqual(mutant['index_document'](**params(raw)),{'error':'UNCLOSED_FENCE'})
