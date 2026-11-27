import inspect
import tempfile
import unittest
from unittest.mock import Mock, patch

from framework import evidence_audit as audit
from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from shadow_runtime.evidence_audit_port import file_evidence_audit
from test_shadow_runtime import ShadowMarkdownStore, bitemp, cspace, ctx, write_req
from test_read_edges import request


class EvidenceAuditTests(unittest.TestCase):
    def test_audit_grant_precedes_reads_and_mutation_exposes_node(self):
        readers=frozenset({'alice'}); node=Node('t1',1,'1'*64,1,readers,readers)
        meta=dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp()),
                  source_attribution={'source_id':'author-1'})
        proof=Mock(return_value=None)
        args=dict(context=ctx(),now=10,view=ReadSnapshot(1,1,{'x':node},{'x':meta}),model=Model(),
                  can_audit=lambda *_:False,proof=proof,limit=1)
        self.assertEqual(audit.evidence_audit(request('x'),**args),{'error':'NOT_FOUND_OR_DENIED'})
        proof.assert_not_called()
        src=inspect.getsource(audit); guard="if can_audit(actor,req['node_id']) is not True:"
        self.assertEqual(src.count(guard),1)
        mutant={}; exec(compile(src.replace(guard,'if False:',1),'<audit-grant-mutant>','exec'),mutant)
        self.assertEqual(mutant['evidence_audit'](request('x'),**args)['locator']['id'],'x')
        proof.assert_called_once()

    def test_mixed_revisions_fail_without_returning_sources(self):
        locator=dict(id='x',revision=1,content_sha='1'*64)
        with patch.object(audit,'read_edges',return_value=dict(locator=locator,edges=[{'untrusted':'sentinel'}])), \
             patch.object(audit,'read_status',return_value=dict(status='verified',locator=dict(locator,revision=2))):
            self.assertEqual(audit.evidence_audit(request('x'),context=ctx(),now=10,view=None,model=None,
                             can_audit=lambda *_:True,proof=None,limit=1),{'error':'EVIDENCE_CHANGED'})

    def test_file_composes_current_revision_and_sources_after_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=ShadowMarkdownStore(tmp,synthetic=True)
            source=s.execute(write_req('source','source fixture',readers=('alice','bob')),ctx(),1)['historical_receipt']
            row=dict(write_req('root','root fixture',readers=('alice','bob')),
                     source_edges=[dict(node_id=source['node_id'],relation='derived',revision=1,content_sha=source['content_sha'])])
            self.assertEqual(s.execute(row,ctx(),3)['outcome'],'ok')
            def report(who='alice', grant=True):
                return file_evidence_audit(ShadowMarkdownStore(tmp,synthetic=True),request('node-2'),
                    context=ctx(who),now=30,can_audit=lambda *_:grant,limit=1)
            self.assertEqual(report(grant=False),{'error':'NOT_FOUND_OR_DENIED'})
            self.assertEqual(report('guest'),{'error':'NOT_FOUND_OR_DENIED'})
            self.assertEqual(report()['verification'],'unverified')
            proof=dict(node_id='node-2',expected_revision=1,verifier_id='fixture-reviewer',scope='full',
                       method_allowed=True,credential_exists=True,credential_time=1,verified_at=10)
            self.assertTrue(s.verify_record(**proof))
            view=report('bob')
            self.assertEqual(set(view),{'locator','verification','sources'})
            self.assertEqual(view['verification'],'verified')
            self.assertEqual(view['sources'],[dict(relation='derived',target=dict(id='node-1',revision=1,
                                                                             content_sha=source['content_sha']))])
            change=dict(row,kind='Write.modify',caller_token='revise',node_id='node-2',expected_revision=1,content='revised fixture')
            self.assertEqual(s.execute(change,ctx(),14)['outcome'],'ok')
            self.assertEqual((report()['locator']['revision'],report()['verification']),(2,'unverified'))
