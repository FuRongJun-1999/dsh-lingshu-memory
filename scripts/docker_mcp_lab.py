"""Reproduce the offline wire and official DSH tool-pipeline labs in Linux Docker."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

from docker_process_lab import ROOT, NO_PROXY_ENV, collect, command

HERE = ROOT / 'scripts'
LOCK = HERE / 'docker_mcp_package-lock.json'
SERVER = 'shadow_runtime/mcp_lab.py'
WIRE = 'scripts/linux_mcp_wire_lab.py'
DSH = 'scripts/linux_dsh_mcp_lab.mjs'


def isolated(*options):
    return ['docker','run','--rm','--pull','never','--cap-drop','ALL','--security-opt','no-new-privileges',
            '--user','65534:65534','--pids-limit','64','--memory','384m',*NO_PROXY_ENV,*options]


def bounded(args, name, timeout):
    try:
        return command(args, timeout)
    except subprocess.TimeoutExpired:
        # A timed-out Docker client need not stop the container itself.
        command(['docker','kill',name], 15)
        raise


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--with-dsh', action='store_true', help='fetch pinned public npm dependencies separately; run workload offline')
    args = cli.parse_args()
    tag = 'node:24-bookworm' if args.with_dsh else 'python:3.11-slim'
    image = json.loads(command(['docker','image','inspect',tag]))[0]
    if image['Os'] != 'linux' or command(['docker','info','--format','{{.OSType}}']).strip() != 'linux':
        cli.error('Linux Docker daemon and image required')
    head = command(['git','rev-parse','HEAD']).strip()
    dirty = bool(command(['git','status','--porcelain']).strip())
    with tempfile.TemporaryDirectory(prefix='lingshu-mcp-code-') as source, tempfile.TemporaryDirectory(prefix='lingshu-mcp-deps-') as dependencies:
        root = Path(source)
        collect(root)
        for rel in (SERVER, DSH if args.with_dsh else WIRE):
            dest = root / rel
            if not dest.is_file():
                shutil.copyfile(ROOT / rel, dest)
        inputs = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
        options = ['--network','none','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777',
                   '--mount',f'type=bind,source={source},target=/exercise,readonly']
        lock_hash = None
        if args.with_dsh:
            raw = LOCK.read_bytes()
            lock_hash = hashlib.sha256(raw).hexdigest()
            (Path(dependencies)/'package-lock.json').write_bytes(raw)
            (Path(dependencies)/'package.json').write_text(json.dumps(dict(name='lingshu-isolated-client-lab',private=True,
                         dependencies=json.loads(raw)['packages']['']['dependencies'])), encoding='utf-8')
            name = 'lingshu-mcp-dependency-' + uuid.uuid4().hex
            # No repo, host home, credential or active npm profile is mounted during this phase.
            bounded(isolated('--name', name, '--mount', f'type=bind,source={dependencies},target=/deps',
                          '--workdir','/deps',image['Id'],'npm','ci','--ignore-scripts','--no-audit','--no-fund',
                          '--registry=https://registry.npmjs.org','--cache=/tmp/npm-cache','--fetch-retries=0'), name, 150)
            if (Path(dependencies)/'package-lock.json').read_bytes() != raw:
                raise RuntimeError('npm lock changed')
            options += ['--mount',f'type=bind,source={dependencies},target=/deps,readonly','--workdir','/deps']
            command_line = ['node','--input-type=module','-e',(root/DSH).read_text(encoding='utf-8')]
        else:
            command_line = ['python','-X','utf8','-B','/exercise/'+WIRE]
        name = 'lingshu-mcp-check-' + uuid.uuid4().hex
        out = bounded(isolated('--name',name,*options,image['Id'],*command_line), name, 85)
    if args.with_dsh:
        lines = [l[len('LAB_RESULT '):] for l in out.splitlines() if l.startswith('LAB_RESULT ')]
        if len(lines) != 1:
            raise RuntimeError('missing or ambiguous official DSH result')
        result = json.loads(lines[0])
        if result['dsh_tool_pipeline'] != 'PASS':
            raise RuntimeError('DSH tool pipeline did not pass')
    else:
        result = json.loads(out)
    if result['audit_rows'] != 1 or result['receipt_replay'] != 'PASS' or result['foreign_read'] != 'DENIED':
        raise RuntimeError('incomplete MCP behavior evidence')
    print(json.dumps(dict(base=head,working_tree_changes=dirty,image=image['Id'],dependencies_sha=lock_hash,
                          source_sha=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest(),run=result), sort_keys=True))


if __name__ == '__main__':
    main()
