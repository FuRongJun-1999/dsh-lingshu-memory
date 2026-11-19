import copy
import dataclasses
import hashlib
import json
import pathlib
import tempfile
import unittest
from framework.contracts import validate_full_response
from framework.spec import canonical
from shadow_runtime.audit import inspect_audit
from shadow_runtime.store import ShadowMarkdownStore
from shadow_runtime.writer_status import WriterStatus
from test_shadow_runtime import ctx, write_req


class WriterReceiptTests(unittest.TestCase):
    def test_replay_preserves_original_writer_across_two_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = WriterStatus(tmp, synthetic=True)
            ha, hb = registry.enroll('a'), registry.enroll('b')
            with self.assertRaises(ValueError):
                ShadowMarkdownStore(tmp,synthetic=True,writer_handle=dataclasses.replace(hb,writer_id='a'))
            a,b = [ShadowMarkdownStore(tmp,synthetic=True,writer_handle=h) for h in (ha,hb)]
            req=write_req('once','synthetic tile'); first=a.execute(req,ctx(),10)
            self.assertEqual(first['outcome'],'ok'); ra=first['historical_receipt']; self.assertEqual(ra['writer_id'],'a')
            for resp in [b.execute(req,ctx(),11), b.execute(dict(kind='Read.receipt',operation='Write.create',caller_token='once'),ctx(),12)]:
                self.assertEqual(resp['outcome'],'ok'); self.assertEqual(resp['historical_receipt'],ra)
            gov=dict(kind='Govern.forget',caller_token='forget',node_id=ra['node_id'],expected_revision=1,reason='fixture')
            rb=b.execute(gov,ctx(),13)['historical_receipt']; self.assertEqual(rb['writer_id'],'b')
            self.assertEqual(a.execute(gov,ctx(),14)['historical_receipt'],rb)
            audit=pathlib.Path(tmp)/'audit/audit.jsonl'; rows=list(map(json.loads,audit.read_text(encoding='utf-8').splitlines()))
            self.assertEqual([(x['writer_id'],x['principal'],x['op']) for x in rows],[('a','alice','Write.create'),('b','alice','Govern.forget')]); self.assertEqual(inspect_audit(audit)['state'],'ok')
            for val in (None,''):
                resp=copy.deepcopy(first);row=dict(rows[0]);del row['entry_sha']
                if val is None: del resp['historical_receipt']['writer_id'];del row['writer_id']
                else: resp['historical_receipt']['writer_id']=val;row['writer_id']=val
                with self.assertRaises(ValueError): validate_full_response(resp)
                row['entry_sha']=hashlib.sha256(canonical(row)).hexdigest();audit.write_bytes((json.dumps(row)+chr(10)).encode());self.assertEqual(inspect_audit(audit)['state'],'integrity_failure')
