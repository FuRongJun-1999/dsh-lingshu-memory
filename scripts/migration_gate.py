"""Isolated migration checks. No legacy installation, user path or deploy action."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framework.migration import load_inventory
from framework.spec import canonical, parse
from shadow_runtime.store import ShadowMarkdownStore


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def locked(name):
    lock = parse((ROOT/'scripts/spec-tree.lock.json').read_text(encoding='utf-8'))
    raw = (ROOT/'spec'/name).read_bytes()
    check(hashlib.sha256(raw).hexdigest()==lock['files'][name], 'fixture or inventory drift: '+name)
    return parse(raw.decode('utf-8'))


def mapping():
    verified = load_inventory()
    check(locked('compatibility.json') == verified, 'inventory changed during check')
    rows = verified['operations']
    return dict(scope='top_level_candidate_mapping', result='PASS', operations=len(rows),
                targets=dict(Counter(x['target'] for x in rows)), runtime_ready=sum(x['runtime_ready'] for x in rows),
                inventory_sha=sha(verified), upstream=verified['upstream_commit'])


def project(response, reference):
    check(response['scope']=='read','wrong response scope')
    if response['outcome']=='error':
        check(all(response[k] is None for k in ('records','target','historical_receipt','next_cursor','selfcheck_aggregate','snapshot_ref','policy_generation')), 'unexpected error payload')
        return response['error_code']
    check(response['outcome']=='ok' and response['error_code'] is None and response['next_cursor'] is None, 'unexpected result')
    check(response['snapshot_ref']=='snap-2-1' and response['policy_generation']==1, 'wrong snapshot')
    if response['records']==[]:
        return 'EMPTY'
    digest = hashlib.sha256(reference.encode()).hexdigest()
    expected = dict(content_type='untrusted_markdown',locator=dict(id='node-1',revision=1,content_sha=digest),body=reference,
                    body_sha=digest, condition_verdict='MATCH',temporal_verdict='MATCH',provenance=None)
    check(response['records']==[expected], 'record, revision, or digest mismatch')
    return 'RECORD'


REASONS = {('RECORD','RECORD'): 'unchanged', ('RECORD','NOT_FOUND_OR_DENIED'): 'reader_ceiling',
           ('RECORD','EMPTY'): 'effective_interval_end', ('RECORD','CONDITION_DEFERRED'): 'unknown_method'}


def assess(cases, observed):
    check(len(cases)==len(observed)==4,'incomplete comparison')
    check(len({case['id'] for case in cases})==4,'duplicate cases')
    results=[]
    for c, item in zip(cases, observed):
        check(c['id']==item['id'] and item['result']==c['expected'], 'unexpected shadow read: '+c['id'])
        reason=REASONS.get((c['reference'],item['result']))
        check(reason is not None and reason==c['reason'],'unexplained difference: '+c['id'])
        results.append(dict(id=c['id'],reference=c['reference'],shadow=item['result'],reason=reason))
    check({x['reason'] for x in results}==set(REASONS.values()), 'missing comparison class')
    return results


def shadow_reads():
    f=locked('migration_shadow_fixture.json'); policy=f['policy']; content=f['content']; cond=policy['condition_space']
    def ctx(who):
        return dict(policy['context'],principal=who)
    with tempfile.TemporaryDirectory() as tmp:
        s=ShadowMarkdownStore(tmp,synthetic=True)
        req=dict(kind='Write.create',caller_token='s4-synthetic',content=content,declared_sensitivity=policy['sensitivity'],
                 reader_ceiling=policy['reader_ceiling'],source_edges=[],condition_space=cond,bitemporal=policy['bitemporal'],
                 source_attribution=dict(source_kind='document',source_id='s4-fixture'),durability_request='process')
        created=s.execute(req,ctx('alice'),10)
        check(created['outcome']=='ok' and created['historical_receipt']['node_id']=='node-1','fixture setup failed')
        # Reopen to read the installed shadow snapshot, not the initial Python object.
        reader=ShadowMarkdownStore(tmp,synthetic=True); observed=[]
        for c in f['cases']:
            query=dict(kind='Read.get',node_id='node-1',include_provenance=False,time_axis='effective',time_point=c['point'],
                       condition_query=dict(cond,method=c['method']))
            observed.append(dict(id=c['id'],result=project(reader.execute(query,ctx(c['principal']),11),content)))
    return dict(scope='synthetic_reference_vs_real_shadow',result='PASS',content_sha=hashlib.sha256(content.encode()).hexdigest(),
                policy_sha=sha(policy),fixture_sha=sha(f),cases=assess(f['cases'],observed),legacy_runtime='NOT_RUN')




def shadow_writes():
    """Exercise only an explicit synthetic temp root; do not accept an external path."""
    from shadow_runtime.writer_status import WriterStatus
    from shadow_runtime.audit import inspect_audit
    f=locked('migration_shadow_fixture.json'); policy=f['policy']; content=f['content']
    raw=content.encode('utf-8'); digest=hashlib.sha256(raw).hexdigest()
    key='s5-reopen'; context=dict(policy['context'],principal='alice')
    req=dict(kind='Write.create',caller_token=key,content=content,declared_sensitivity=policy['sensitivity'],
             reader_ceiling=policy['reader_ceiling'],source_edges=[],condition_space=policy['condition_space'],
             bitemporal=policy['bitemporal'],source_attribution=dict(source_kind='document',source_id='s5-fixture'),durability_request='process')
    scope=dict(tenant=context['tenant'],principal='alice',operation='Write.create',caller_token=key)
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp); ids=WriterStatus(root,synthetic=True)
        first=ShadowMarkdownStore(root,synthetic=True,writer_handle=ids.enroll('s5-origin'))
        out=first.execute(req,context,10); check(out['outcome']=='ok','write not accepted'); receipt=out['historical_receipt']
        expected=dict(writer_id='s5-origin',node_id='node-1',revision=1,content_sha=digest,commit_status='committed',durability_actual='process',audit_state='ok')
        check(all(receipt.get(k)==v for k,v in expected.items()),'wrong initial receipt')
        other=ShadowMarkdownStore(root,synthetic=True,writer_handle=ids.enroll('s5-reader'))
        def recover(): return other.recover_token_state(**scope)
        healthy=dict(commit_status='committed',audit_state='ok',integrity_failure=False)
        check(recover()==healthy,'wrong recovery after reopen')
        replay=other.execute(req,context,11);check(replay['outcome']=='ok' and replay['historical_receipt']==receipt,'replay changed receipt')
        conflict=other.execute(dict(req,content='different fixture text'),context,12)
        check(conflict['error_code']=='TOKEN_PAYLOAD_CONFLICT' and conflict['historical_receipt'] is None,'token conflict not rejected')
        audit=root/'audit/audit.jsonl'; ai=inspect_audit(audit,expected_tenant=context['tenant'])
        check(ai['state']=='ok' and ai['count']==1,'audit duplicated or missing')
        event=parse(audit.read_text(encoding='utf-8'));check(all(event.get(k)==v for k,v in dict(writer_id='s5-origin',op='Write.create',node_id='node-1',revision=1,payload_sha=digest).items()),'audit not bound')
        paths=list((root/'nodes').glob('*/rev_*.md'));check(len(paths)==1 and paths[0].read_bytes()==raw,'wrong persisted bytes')
        meta=parse(paths[0].with_suffix('.meta.json').read_text(encoding='utf-8'));check(meta['tenant']==context['tenant'] and meta['current_readers']==policy['reader_ceiling'] and meta['declared_sensitivity']==policy['sensitivity'] and meta['bitemporal']==policy['bitemporal'] and meta['content_sha']==digest,'wrong installed metadata')
        paths[0].write_bytes(raw+b'!'); broken=recover()
        check(broken==dict(commit_status='unknown',audit_state='ok',integrity_failure=True),'damaged bytes accepted')
        paths[0].write_bytes(raw);check(recover()==healthy,'restored fixture not recovered')
    return dict(result='PASS',scope='isolated_process_durability',content_sha=digest,policy_sha=sha(policy),replayed_original=True,audit_rows=1,damaged=broken['commit_status'],restored='committed',legacy_runtime='NOT_RUN',power_loss='NOT_RUN')




def baseline():
    m=load_inventory(); check(m==locked('compatibility.json'),'inventory drift')
    f=locked('migration_shadow_fixture.json'); api=locked('api_v2.schema.json'); bench=locked('benchmark_cases.json')
    ctx=f['policy']['context']; check(set(ctx)=={'auth_epoch','clearance','expires_at','policy_generation','tenant'},'context shape drift')
    check(f['policy']['reader_ceiling']==['alice'] and {c['principal'] for c in f['cases']}=={'alice','bob'},'permission fixtures missing')
    check(len(bench['cases'])==39 and len(f['cases'])==4,'incomplete query baseline')
    return dict(result='PASS',scope='pinned_top_level_and_synthetic_fields',upstream=m['upstream_commit'],source_sha=m['source_sha256'],inventory_sha=sha(m),request_fields_sha=sha(api),query_cases_sha=sha(bench),policy_sha=sha(f['policy']),legacy_action_parameters='NOT_RUN')


def checked_suite(pattern,expected):
    import unittest
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern=pattern)
    result=unittest.TestResult(); suite.run(result)
    check(result.wasSuccessful() and result.testsRun==expected and not result.skipped and not result.expectedFailures and not result.unexpectedSuccesses,'migration behavior check failed: '+pattern)
    return result.testsRun


def behavior():
    # Run only the historical baseline suite and its mutation driver, not this stage recursively.
    n=checked_suite('test_migration.py',11)
    m=checked_suite('test_migration_mutations.py',1)
    return dict(result='PASS',scope='isolated_behavior_and_mutation_driver',behavior_tests=n,mutation_drivers=m,legacy_runtime='NOT_RUN')


REFERENCE_FILES=('LICENSE','framework/__init__.py','framework/migration.py','framework/spec.py','framework/api.py','spec/compatibility.json')


def check_bundle(path):
    import zipfile
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        check(len(names)==len(REFERENCE_FILES) and set(names)==set(REFERENCE_FILES),'wrong reference package contents')
        for name in REFERENCE_FILES:
            check(archive.read(name)==(ROOT/name).read_bytes(),'wrong package bytes: '+name)


def package_smoke():
    import zipfile, os, subprocess
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as tmp:
        base=Path(tmp); archive=base/'reference.zip'; dest=base/'installed'; dest.mkdir()
        with zipfile.ZipFile(archive,'w') as z:
            for name in REFERENCE_FILES: z.write(ROOT/name,name)
        check_bundle(archive)
        with zipfile.ZipFile(archive) as z: z.extractall(dest)
        # Isolated interpreter with only this temporary install added to its module path.
        code=('import sys,pathlib,json; root=pathlib.Path(sys.argv[1]).resolve(); sys.path.insert(0,str(root)); '
              'from framework import migration; assert pathlib.Path(migration.__file__).resolve().is_relative_to(root); '
              'print(json.dumps([migration.operation_plan("cg","read"),migration.operation_plan("cg","not-an-op")]))')
        q=subprocess.run([sys.executable,'-I','-B','-c',code,str(dest)],cwd=base,env=dict(os.environ,PYTHONUTF8='1'),shell=False,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
        check(q.returncode==0,'reference install import failed: '+q.stderr[-250:]); observations=parse(q.stdout)
        check(observations==[dict(decision='specification_only',target='Read',runtime_ready=False),dict(decision='reject',target=None,runtime_ready=False)],'wrong installed behavior')
        return dict(result='PASS', scope='temporary_reference_bundle_only', entries=len(REFERENCE_FILES), license_sha=hashlib.sha256((dest/'LICENSE').read_bytes()).hexdigest(),production_installer='NOT_RUN')


def rollout():
    from scripts.release_gate import evaluate
    register=locked('acceptance.status.json'); status=evaluate(register,ROOT/'docs/release-evidence')
    # This isolated repository has no trusted rollout authority or control plane. Never synthesize one.
    missing=['NO_TRUSTED_ROLLOUT_AUTHORIZATION','NO_VERIFIED_PRODUCTION_ROLLBACK']
    if register['candidate'] is None: missing.append('NO_BOUND_CANDIDATE')
    if status['production']['state']!='ELIGIBLE': missing.append('PRODUCTION_EVIDENCE_INCOMPLETE')
    return dict(result='BLOCK',scope='production_rollout',reasons=missing,release=status['production'],effects=0)


def main():
    cli=argparse.ArgumentParser(description=__doc__); cli.add_argument('--stage',choices=['S0','S1','S2','S3','S4','S5','S6']); args=cli.parse_args()
    report={}
    for stage,run in [('S0',baseline),('S1',behavior),('S2',package_smoke),('S3',mapping),('S4',shadow_reads),('S5',shadow_writes),('S6',rollout)]:
        if args.stage in (None,stage):
            try: report[stage]=run()
            except (ValueError, OSError, KeyError, TypeError) as e: report[stage]={'result':'FAIL','error':str(e)}
    print(json.dumps(report,sort_keys=True))
    if any(x['result']=='FAIL' for x in report.values()): return 1
    return 3 if args.stage=='S6' and report['S6']['result']=='BLOCK' else 0

if __name__=='__main__': raise SystemExit(main())
