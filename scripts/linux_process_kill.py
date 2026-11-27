"""Run real process-kill checks on an isolated Linux filesystem (not a power-loss test)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shadow_runtime.audit import inspect_audit
from shadow_runtime.store import ShadowMarkdownStore

POINTS = {"manifest:before_replace": False, "manifest:after_replace": True, "audit:after_append": True}
BODY = "synthetic docker blue tile"
TOKEN = "docker-process-fixture"


def require(condition, detail):
    if not condition:
        raise AssertionError(detail)


def fixture():
    conditions = dict(carrier=dict(state="declared", text="md"), method=dict(state="declared", text="exact"),
                      existence=dict(state="declared", text="present"), attributes=[])
    interval = dict(start=dict(state="instant", value="2024-01-01T00:00:00Z"), end=dict(state="instant", value="2024-01-10T00:00:00Z"))
    request = dict(kind="Write.create", caller_token=TOKEN, content=BODY, declared_sensitivity=1,
                   reader_ceiling=["alice"], source_edges=[], condition_space=conditions,
                   bitemporal=dict(observed=interval, effective=interval),
                   source_attribution=dict(source_kind="document", source_id="fixture"), durability_request="process")
    context = dict(tenant="fixture", principal="alice", clearance=2, auth_epoch=1, policy_generation=1, expires_at=1000)
    get = dict(kind="Read.get", node_id="node-1", include_provenance=False, condition_query=conditions,
               time_axis="effective", time_point="2024-01-05T00:00:00Z")
    return request, context, get


def barrier(point, store):
    def stop(stage, _path):
        if stage == point:
            print(json.dumps(dict(stage=stage, pid=os.getpid(), writer=store._writer_id)), flush=True)
            sys.stdin.buffer.read(1)
            raise RuntimeError("fault barrier released without SIGKILL")
    return stop


def worker(root, point=None):
    request, context, get = fixture()
    store = ShadowMarkdownStore(root, synthetic=True)
    if point is not None:
        store.execute(request, context, 10, fault_hook=barrier(point, store))
        raise RuntimeError("fault barrier not reached")
    recovered = store.recover_token_state(tenant="fixture", principal="alice", operation="Write.create", caller_token=TOKEN)
    retry = store.execute(request, context, 11)
    own = store.execute(get, context, 12)
    foreign = store.execute(get, dict(context, principal="bob"), 12)
    audit_path = Path(root) / "audit/audit.jsonl"
    audit = inspect_audit(audit_path, expected_tenant="fixture")
    rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()] if audit_path.exists() else []
    bodies = sorted(p.read_bytes().hex() for p in (Path(root)/"nodes").rglob("*.md"))
    print(json.dumps(dict(pid=os.getpid(), recovered=recovered, retry=retry, own=own, foreign=foreign,
                          audit=audit, rows=rows, bodies=bodies)))


def kill_and_reopen(root, point, mode):
    argv = [sys.executable, "-X", "utf8", "-B", __file__]
    with subprocess.Popen([*argv, "--child-root", str(root), "--point", point, *mode], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace") as proc:
        try:
            with selectors.DefaultSelector() as io:
                io.register(proc.stdout, selectors.EVENT_READ)
                require(io.select(timeout=15), "no fault checkpoint")
                marker = json.loads(proc.stdout.readline())
            require(marker["pid"] == proc.pid and marker["stage"] == point, "wrong fault checkpoint")
            os.kill(proc.pid, signal.SIGKILL)
            rest, stderr = proc.communicate(timeout=10)
            require(proc.returncode == -signal.SIGKILL and not rest.strip() and not stderr.strip(),
                    (proc.returncode, rest, stderr))
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate(timeout=10)
    child = subprocess.run([*argv, "--child-root", str(root), *mode], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", shell=False, timeout=20)
    require(child.returncode == 0, child.stderr)
    return proc.pid, proc.returncode, marker, json.loads(child.stdout)


def run_case(root, point, committed):
    pid, exitcode, marker, obs = kill_and_reopen(root, point, [])
    state = "committed" if committed else "unknown"
    require(obs["pid"] != pid and obs["recovered"]["commit_status"] == state, obs)
    require(obs["retry"]["target"]["commit_status"] == state and not obs["recovered"]["integrity_failure"], obs)
    require(obs["foreign"]["error_code"] == "NOT_FOUND_OR_DENIED" and obs["foreign"]["records"] is None, obs)
    if committed:
        receipt = obs["retry"]["historical_receipt"]
        digest = hashlib.sha256(BODY.encode()).hexdigest()
        require(obs["retry"]["outcome"] == "ok" and receipt["writer_id"] == marker["writer"], obs)
        records = obs["own"]["records"]
        require(len(records) == 1 and records[0]["body"] == BODY and records[0]["locator"] ==
                dict(id="node-1", revision=1, content_sha=digest), obs)
        require(obs["bodies"] == [BODY.encode().hex()] and obs["audit"]["state"] == "ok" and len(obs["rows"]) == 1, obs)
        row = obs["rows"][0]
        require(obs["audit"]["count"] == 1 and row["writer_id"] == marker["writer"] and row["ts"] == 10
                and row["payload_sha"] == digest, obs)
    else:
        require(obs["retry"]["error_code"] == "RECOVERY_UNCERTAIN" and obs["retry"]["historical_receipt"] is None
                and obs["own"]["error_code"] == "NOT_FOUND_OR_DENIED" and obs["own"]["records"] is None
                and not obs["bodies"] and not obs["rows"] and obs["audit"]["state"] == "missing", obs)
    return dict(point=point, killed_pid=pid, exit=exitcode, reader_pid=obs["pid"],
                commit_status=state, audit_rows=obs["audit"]["count"], foreign_denied=True,
                original_writer_preserved=committed)


def governance_worker(root, point):
    request, context, get = fixture()
    store = ShadowMarkdownStore(root, synthetic=True)
    govern = dict(kind='Govern.forget', caller_token='fixture-forget', node_id='node-1',
                  expected_revision=1, reason='synthetic retirement')
    if point is not None:
        require(store.execute(request, context, 9)['outcome'] == 'ok', 'setup write failed')
        store.execute(govern, context, 10, fault_hook=barrier(point, store))
        raise RuntimeError('governance barrier not reached')
    rec = store.recover_token_state(tenant='fixture', principal='alice', operation=govern['kind'],
                                    caller_token=govern['caller_token'])
    replay = store.execute(govern, context, 11)
    own = store.execute(get, context, 12)
    audit = Path(root) / 'audit/audit.jsonl'
    rows = [json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines()]
    bodies = sorted(p.read_bytes().hex() for p in (Path(root)/'nodes').rglob('*.md'))
    print(json.dumps(dict(pid=os.getpid(), recovered=rec, replay=replay, own=own, rows=rows, bodies=bodies,
                          audit=inspect_audit(audit, expected_tenant='fixture'))))


def run_governance_case(root, point, committed):
    pid, exitcode, marker, obs = kill_and_reopen(root, point, ['--governance'])
    state = 'committed' if committed else 'unknown'
    require(obs['pid'] != pid and not obs['recovered']['integrity_failure'] and
            obs['recovered']['commit_status'] == obs['replay']['target']['commit_status'] == state, obs)
    require(obs['bodies'] == [BODY.encode().hex()] and obs['audit']['state'] == 'ok', obs)
    rows = obs['rows']
    require([row['op'] for row in rows] == (['Write.create', 'Govern.forget'] if committed else ['Write.create']), obs)
    if committed:
        require(obs['replay']['outcome'] == 'ok' and obs['replay']['historical_receipt']['writer_id'] == marker['writer']
                and rows[1]['writer_id'] == marker['writer'] and rows[1]['ts'] == 10, obs)
        require(obs['own']['error_code'] == 'NOT_FOUND_OR_DENIED' and obs['own']['records'] is None, obs)
    else:
        require(obs['replay']['error_code'] == 'RECOVERY_UNCERTAIN' and obs['replay']['historical_receipt'] is None, obs)
        require([rec['body'] for rec in obs['own']['records']] == [BODY], obs)
    return dict(point=point, killed_pid=pid, exit=exitcode, reader_pid=obs['pid'], commit_status=state,
                audit_rows=len(rows), read_after='denied' if committed else 'visible')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isolated", action="store_true")
    parser.add_argument("--child-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--point", choices=POINTS, help=argparse.SUPPRESS)
    parser.add_argument("--governance", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("requires Linux")
    if args.child_root is not None:
        if args.isolated:
            parser.error("child mode is internal")
        (governance_worker if args.governance else worker)(args.child_root, args.point)
        return
    if not args.isolated or args.point or args.governance:
        parser.error("use --isolated; no external storage path")
    with tempfile.TemporaryDirectory(prefix="lingshu-kill-") as directory:
        results = [run_case(Path(directory)/str(i), point, expected) for i, (point, expected) in enumerate(POINTS.items())]
        governance = [run_governance_case(Path(directory)/('govern-'+str(i)), point, expected)
                      for i, (point, expected) in enumerate(POINTS.items())]
    print(json.dumps(dict(schema=2, governance_cases=governance, os=sys.platform, kernel=os.uname().release, python=sys.version.split()[0],
                          cases=results, power_loss="NOT_RUN", dsh_host="NOT_RUN", production="NOT_RUN"), sort_keys=True))


if __name__ == "__main__":
    main()
