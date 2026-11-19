import copy
import unittest
from scripts import migration_gate as gate


class MigrationGateTests(unittest.TestCase):
    def test_inventory_does_not_grant_runtime_readiness(self):
        out=gate.mapping(); self.assertEqual(out['targets'],{'Read':4,'Write':1,'Govern':1,'extension':38}); self.assertEqual((out['operations'],out['runtime_ready']),(44,0))

    def test_real_shadow_with_independent_expected_differences(self):
        out=gate.shadow_reads(); self.assertEqual(out['legacy_runtime'],'NOT_RUN'); self.assertEqual([(x['id'],x['shadow']) for x in out['cases']], [('inside','RECORD'),('other-reader','NOT_FOUND_OR_DENIED'),('exclusive-end','EMPTY'),('unknown-method','CONDITION_DEFERRED')])

    def test_unexpected_or_unexplained_change_is_not_accepted(self):
        cases=gate.locked('migration_shadow_fixture.json')['cases']; obs=[dict(id=c['id'],result=c['expected']) for c in cases]
        self.assertEqual(len(gate.assess(cases,obs)),4)
        for index,field,value in [(1,'result','RECORD'),(0,'id','missing')]:
            wrong=copy.deepcopy(obs); wrong[index][field]=value
            with self.assertRaises(ValueError): gate.assess(cases,wrong)
        wrong=copy.deepcopy(cases);wrong[1]['reason']='unchanged'
        with self.assertRaises(ValueError): gate.assess(wrong,obs)
        with self.assertRaises(ValueError): gate.assess(cases[:-1],obs[:-1])

    def test_error_code_alone_cannot_hide_data(self):
        err=dict(scope='read',outcome='error',error_code='NOT_FOUND_OR_DENIED',records=None,target=None,historical_receipt=None,next_cursor=None,selfcheck_aggregate=None,snapshot_ref=None,policy_generation=None)
        self.assertEqual(gate.project(err,'unused'),'NOT_FOUND_OR_DENIED')
        with self.assertRaises(ValueError): gate.project(dict(err,records=[{'body':'unexpected'}]),'unused')

    def test_reopened_write_reconciles_original_audit_and_fault(self):
        out=gate.shadow_writes()
        self.assertEqual((out['scope'],out['audit_rows'],out['replayed_original']),('isolated_process_durability',1,True))
        self.assertEqual((out['damaged'],out['restored'],out['power_loss']),('unknown','committed','NOT_RUN'))

    def test_s5_rejects_recovery_that_blindly_claims_committed(self):
        from unittest.mock import patch
        fake=dict(commit_status='committed',audit_state='ok',integrity_failure=False)
        with patch.object(gate.ShadowMarkdownStore,'recover_token_state',return_value=fake):
            with self.assertRaisesRegex(ValueError,'damaged bytes accepted'): gate.shadow_writes()

    def test_reference_archive_rejects_missing_license_or_additional_test(self):
        import zipfile, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            for missing,extra in ((True,False),(False,True)):
                p=Path(tmp)/'sample.zip'
                with zipfile.ZipFile(p,'w') as z:
                    for n in gate.REFERENCE_FILES:
                        if not (missing and n=='LICENSE'):z.write(gate.ROOT/n,n)
                    if extra:z.writestr('tests/not_shipped.py','')
                with self.assertRaisesRegex(ValueError,'wrong reference package contents'):gate.check_bundle(p)

    def test_isolated_rollout_never_synthesizes_authorization(self):
        from unittest.mock import patch
        self.assertIn('PRODUCTION_EVIDENCE_INCOMPLETE',gate.rollout()['reasons'])
        with patch('scripts.release_gate.evaluate',return_value={'production':{'state':'ELIGIBLE','missing_pass':[]}}):
            out=gate.rollout(); self.assertEqual((out['result'],out['effects']),('BLOCK',0)); self.assertIn('NO_TRUSTED_ROLLOUT_AUTHORIZATION',out['reasons']);self.assertNotIn('PRODUCTION_EVIDENCE_INCOMPLETE',out['reasons'])
