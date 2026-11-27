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
    return dict(cases=cases, file_tests=4, verification_tests=3, status_tests=3, dsh_model_loop='NOT_RUN', production='NOT_RUN')


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
        fixtures = ('test_read_status.py','test_verification_capability.py','test_file_recall.py','test_shadow_runtime.py','test_sandbox_controller.py','test_sandbox_store.py')
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
