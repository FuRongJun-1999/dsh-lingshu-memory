"""在隔离容器内以独立子进程复验固定任务的实际调用。"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

from docker_process_lab import ROOT, IMAGE, NO_PROXY_ENV, collect, command


def observe():
    fixture = json.loads((ROOT/'spec/context_demo.json').read_text(encoding='utf-8'))
    expected = fixture['fixture'][0]['body']
    cases = {}
    for label, code, status, reason, operations in (
        ('ready', 0, 'ready', None, ['search','get','search','get','get']),
        ('wrong_version', 3, 'blocked', 'EVIDENCE_GAP', ['search','get','search','get']),
        ('zero_calls', 3, 'blocked', 'BUDGET', []),
    ):
        packet = copy.deepcopy(fixture)
        if label == 'wrong_version':
            packet['fixture'][0]['version'] = 'v2'
        elif label == 'zero_calls':
            packet['task']['budget']['calls'] = 0
        p = subprocess.run([sys.executable,'-X','utf8','-B','-m','sandbox_runtime.cli','--synthetic'],
                           cwd=ROOT, env=dict(os.environ,PYTHONUTF8='1'), input=json.dumps(packet),
                           shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=15)
        if p.returncode != code or p.stderr:
            raise RuntimeError(label+' unexpected process result')
        report = json.loads(p.stdout)
        actual = report['output']
        if actual['status'] != status or [a['operation'] for a in report['actions']] != operations:
            raise RuntimeError(label+' incorrect status or observed calls')
        if status == 'ready':
            from framework.spec import digest
            import hashlib
            locator = {'id':fixture['fixture'][0]['id'],'revision':1,'content_sha':hashlib.sha256(expected.encode()).hexdigest()}
            if actual != {'status':'ready','task_sha':digest(packet['task']),'records':[{'body':expected,'citation':locator}]} or report['alerts']:
                raise RuntimeError('incorrect retrieved evidence')
        elif actual != {'status':'blocked','reason':reason} or report['alerts'] != [{'event':'alert','reason':reason}]:
            raise RuntimeError(label+' incorrect failure or alert')
        cases[label] = dict(exit=code,status=status,reason=reason,operations=operations)
    suite = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_file_recall.py','-v'],
                           cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if suite.returncode or 'Ran 4 tests' not in suite.stderr or not suite.stderr.rstrip().endswith('OK'):
        raise RuntimeError('file recall tests failed: '+suite.stderr)
    proof = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_verification_capability.py','-v'],
                           cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if proof.returncode or 'Ran 3 tests' not in proof.stderr or not proof.stderr.rstrip().endswith('OK'):
        raise RuntimeError('proof tests failed: '+proof.stderr)
    status = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_read_status.py','-v'],
                            cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if status.returncode or 'Ran 3 tests' not in status.stderr or not status.stderr.rstrip().endswith('OK'):
        raise RuntimeError('status tests failed: '+status.stderr)
    edges = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_read_edges.py','-v'],
                           cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if edges.returncode or 'Ran 3 tests' not in edges.stderr or not edges.stderr.rstrip().endswith('OK'):
        raise RuntimeError('edge tests failed: '+edges.stderr)
    relations = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_time_relation.py','-v'],
                               cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if relations.returncode or 'Ran 3 tests' not in relations.stderr or not relations.stderr.rstrip().endswith('OK'):
        raise RuntimeError('relation tests failed: '+relations.stderr)
    timeline = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_read_timeline.py','-v'],
                              cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if timeline.returncode or 'Ran 3 tests' not in timeline.stderr or not timeline.stderr.rstrip().endswith('OK'):
        raise RuntimeError('timeline tests failed: '+timeline.stderr)
    anchors = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_time_anchors.py','-v'],
                             cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if anchors.returncode or 'Ran 3 tests' not in anchors.stderr or not anchors.stderr.rstrip().endswith('OK'):
        raise RuntimeError('anchor tests failed: '+anchors.stderr)
    time_check = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_time_consistency.py','-v'],
                                cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if time_check.returncode or 'Ran 3 tests' not in time_check.stderr or not time_check.stderr.rstrip().endswith('OK'):
        raise RuntimeError('time consistency tests failed: '+time_check.stderr)
    state_chain = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_state_chain.py','-v'],
                                 cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if state_chain.returncode or 'Ran 4 tests' not in state_chain.stderr or not state_chain.stderr.rstrip().endswith('OK'):
        raise RuntimeError('state chain tests failed: '+state_chain.stderr)
    event_port = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_state_event_port.py','-v'],
                                 cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if event_port.returncode or 'Ran 4 tests' not in event_port.stderr or not event_port.stderr.rstrip().endswith('OK'):
        raise RuntimeError('state event tests failed: '+event_port.stderr)
    lease = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_state_lease.py','-v'],
                           cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if lease.returncode or 'Ran 3 tests' not in lease.stderr or not lease.stderr.rstrip().endswith('OK'):
        raise RuntimeError('state lease tests failed: '+lease.stderr)
    audit = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_evidence_audit.py','-v'],
                           cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if audit.returncode or 'Ran 3 tests' not in audit.stderr or not audit.stderr.rstrip().endswith('OK'):
        raise RuntimeError('evidence audit tests failed: '+audit.stderr)
    hints = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_route_candidates.py','-v'],
                           cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if hints.returncode or 'Ran 3 tests' not in hints.stderr or not hints.stderr.rstrip().endswith('OK'):
        raise RuntimeError('route tests failed: '+hints.stderr)
    help_suite = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_capability_help.py','-v'],
                                cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if help_suite.returncode or 'Ran 3 tests' not in help_suite.stderr or not help_suite.stderr.rstrip().endswith('OK'):
        raise RuntimeError('capability help tests failed: '+help_suite.stderr)
    progress = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_task_progress.py','-v'],
                               cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if progress.returncode or 'Ran 3 tests' not in progress.stderr or not progress.stderr.rstrip().endswith('OK'):
        raise RuntimeError('task progress tests failed: '+progress.stderr)
    refs = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_source_ref.py','-v'],
                           cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if refs.returncode or 'Ran 3 tests' not in refs.stderr or not refs.stderr.rstrip().endswith('OK'):
        raise RuntimeError('source ref tests failed: '+refs.stderr)
    docs = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_document_sections.py','-v'],
                           cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if docs.returncode or 'Ran 3 tests' not in docs.stderr or not docs.stderr.rstrip().endswith('OK'):
        raise RuntimeError('document reference tests failed: '+docs.stderr)
    code = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_python_declarations.py','-v'],
                           cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if code.returncode or 'Ran 3 tests' not in code.stderr or not code.stderr.rstrip().endswith('OK'):
        raise RuntimeError('Python declaration tests failed: '+code.stderr)
    recent = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_recent_window.py','-v'],
                            cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if recent.returncode or 'Ran 3 tests' not in recent.stderr or not recent.stderr.rstrip().endswith('OK'):
        raise RuntimeError('recent window tests failed: '+recent.stderr)
    resume = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_session_resume.py','-v'],
                            cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if resume.returncode or 'Ran 3 tests' not in resume.stderr or not resume.stderr.rstrip().endswith('OK'):
        raise RuntimeError('session resume tests failed: '+resume.stderr)
    causal = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_causal_path.py','-v'],
                            cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if causal.returncode or 'Ran 3 tests' not in causal.stderr or not causal.stderr.rstrip().endswith('OK'):
        raise RuntimeError('causal path tests failed: '+causal.stderr)
    protection = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_protection_check.py','-v'],
                                 cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if protection.returncode or 'Ran 3 tests' not in protection.stderr or not protection.stderr.rstrip().endswith('OK'):
        raise RuntimeError('protection check tests failed: '+protection.stderr)
    goals = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_goal_list.py','-v'],
                            cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if goals.returncode or 'Ran 3 tests' not in goals.stderr or not goals.stderr.rstrip().endswith('OK'):
        raise RuntimeError('goal list tests failed: '+goals.stderr)
    lineage = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_read_lineage.py','-v'],
                              cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if lineage.returncode or 'Ran 3 tests' not in lineage.stderr or not lineage.stderr.rstrip().endswith('OK'):
        raise RuntimeError('lineage tests failed: '+lineage.stderr)
    history = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_condition_history.py','-v'],
                              cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if history.returncode or 'Ran 3 tests' not in history.stderr or not history.stderr.rstrip().endswith('OK'):
        raise RuntimeError('condition history tests failed: '+history.stderr)
    records = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_review_records.py','-v'],
                              cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if records.returncode or 'Ran 3 tests' not in records.stderr or not records.stderr.rstrip().endswith('OK'):
        raise RuntimeError('review records tests failed: '+records.stderr)
    records = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_condition_conflict.py','-v'],
                              cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if records.returncode or 'Ran 3 tests' not in records.stderr or not records.stderr.rstrip().endswith('OK'):
        raise RuntimeError('review records tests failed: '+records.stderr)
    records = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_export_locators.py','-v'],
                              cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if records.returncode or 'Ran 3 tests' not in records.stderr or not records.stderr.rstrip().endswith('OK'):
        raise RuntimeError('review records tests failed: '+records.stderr)
    records = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_verification_age.py','-v'],
                              cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if records.returncode or 'Ran 3 tests' not in records.stderr or not records.stderr.rstrip().endswith('OK'):
        raise RuntimeError('review records tests failed: '+records.stderr)
    records = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_identity_profile.py','-v'],
                              cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if records.returncode or 'Ran 3 tests' not in records.stderr or not records.stderr.rstrip().endswith('OK'):
        raise RuntimeError('review records tests failed: '+records.stderr)
    records = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_self_state_card.py','-v'],
                              cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if records.returncode or 'Ran 3 tests' not in records.stderr or not records.stderr.rstrip().endswith('OK'):
        raise RuntimeError('review records tests failed: '+records.stderr)
    records = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_calibration_report.py','-v'],
                              cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if records.returncode or 'Ran 3 tests' not in records.stderr or not records.stderr.rstrip().endswith('OK'):
        raise RuntimeError('review records tests failed: '+records.stderr)
    records = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_index_info.py','-v'],
                              cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if records.returncode or 'Ran 3 tests' not in records.stderr or not records.stderr.rstrip().endswith('OK'):
        raise RuntimeError('review records tests failed: '+records.stderr)
    records = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_theory_declaration.py','-v'],
                              cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if records.returncode or 'Ran 3 tests' not in records.stderr or not records.stderr.rstrip().endswith('OK'):
        raise RuntimeError('review records tests failed: '+records.stderr)
    records = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_heartbeat_status.py','-v'],
                              cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if records.returncode or 'Ran 3 tests' not in records.stderr or not records.stderr.rstrip().endswith('OK'):
        raise RuntimeError('review records tests failed: '+records.stderr)
    records = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_ingest_preview.py','-v'],
                              cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if records.returncode or 'Ran 3 tests' not in records.stderr or not records.stderr.rstrip().endswith('OK'):
        raise RuntimeError('review records tests failed: '+records.stderr)
    records = subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_propagation_preview.py','-v'],
                              cwd=ROOT,shell=False,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=40)
    if records.returncode or 'Ran 3 tests' not in records.stderr or not records.stderr.rstrip().endswith('OK'):
        raise RuntimeError('review records tests failed: '+records.stderr)
    return dict(cases=cases, file_tests=4, verification_tests=3, status_tests=3, edge_tests=3, relation_tests=3, timeline_tests=3, anchor_tests=3, time_check_tests=3, state_chain_tests=4, state_event_tests=4, state_lease_tests=3, evidence_audit_tests=3, route_tests=3, help_tests=3, task_progress_tests=3, source_ref_tests=3, document_section_tests=3, python_declaration_tests=3, recent_window_tests=3, session_resume_tests=3, causal_path_tests=3, protection_check_tests=3, goal_list_tests=3, lineage_tests=3, condition_history_tests=3, review_records_tests=3, condition_conflict_tests=3, export_locator_tests=3, verification_age_tests=3, identity_profile_tests=3, self_state_card_tests=3, calibration_report_tests=3, index_info_tests=3, theory_declaration_tests=3, heartbeat_status_tests=3, ingest_preview_tests=3, propagation_preview_tests=3,
                dsh_model_loop='NOT_RUN', production='NOT_RUN')


def main():
    import hashlib
    import tempfile
    import uuid
    name = 'lingshu-recall-check-' + uuid.uuid4().hex
    image = json.loads(command(['docker','image','inspect',IMAGE]))[0]
    if image['Os'] != 'linux' or command(['docker','info','--format','{{.OSType}}']).strip() != 'linux':
        raise RuntimeError('Linux Docker required')
    with tempfile.TemporaryDirectory(prefix='lingshu-recall-code-') as tmp:
        root = Path(tmp)
        sources = collect(root)
        fixtures = ('test_propagation_preview.py','test_ingest_preview.py','test_heartbeat_status.py','test_theory_declaration.py','test_index_info.py','test_calibration_report.py','test_self_state_card.py','test_identity_profile.py','test_verification_age.py','test_export_locators.py','test_condition_conflict.py','test_review_records.py','test_condition_history.py','test_read_lineage.py','test_goal_list.py','test_protection_check.py','test_causal_path.py','test_session_resume.py','test_recent_window.py','test_python_declarations.py','test_document_sections.py','test_source_ref.py','test_task_progress.py','test_capability_help.py','test_route_candidates.py','test_evidence_audit.py','test_state_lease.py','test_state_event_port.py','test_state_chain.py','test_time_consistency.py','test_time_anchors.py','test_read_timeline.py','test_time_relation.py','test_read_edges.py','test_read_status.py','test_verification_capability.py','test_file_recall.py','test_shadow_runtime.py','test_sandbox_controller.py','test_sandbox_store.py')
        for rel in ('scripts/docker_process_lab.py', 'scripts/docker_context_lab.py', *(f'tests/{n}' for n in fixtures)):
            dest = root/rel
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes((ROOT/rel).read_bytes())
        hashes = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in root.rglob('*') if p.is_file()}
        argv = ['docker','run','--rm','--name',name,'--pull','never','--network','none',*NO_PROXY_ENV,
                '--read-only','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=128m,mode=1777','--cap-drop','ALL','--security-opt','no-new-privileges','--user','65534:65534',
                '--pids-limit','64','--memory','384m','--mount',f'type=bind,source={tmp},target=/exercise,readonly',
                image['Id'],'python','-X','utf8','-B','/exercise/scripts/docker_context_lab.py','--inside']
        try:
            result = json.loads(command(argv,90))
        except subprocess.TimeoutExpired:
            command(['docker','kill',name],15)
            raise
    if len(result['cases']) != 3:
        raise RuntimeError('missing case results')
    print(json.dumps(dict(base=command(['git','rev-parse','HEAD']).strip(),image=image['Id'],
                          source_sha=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),
                          collected_sha=sources,run=result), sort_keys=True))


if __name__ == '__main__':
    if sys.argv[1:] == ['--inside']:
        sys.path.insert(0,str(ROOT))
        print(json.dumps(observe(),sort_keys=True))
    elif len(sys.argv) == 1:
        main()
    else:
        raise SystemExit('unexpected arguments')
