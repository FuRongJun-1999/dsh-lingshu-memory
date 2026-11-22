"""Validate a stage evidence manifest (self-verification protocol, schema v3).

Read-only. Evidence is anchored to committed bytes; the validator never writes
acceptance status, release gates or production records."""
import argparse
import datetime
import hashlib
import json
import pathlib
import re
import subprocess
import sys

LEVELS = {'I0': 0, 'I1': 1, 'I2': 2, 'I3': 3, 'I4': 4}
SCOPES = ('isolated', 'production')
ROLES = ('independent-verifier', 'stage-gate-reviewer')
EVIDENCE_PREFIX = 'evidence/'
FORBIDDEN_PREFIX = ('scripts/', 'tests/', 'docs/', 'spec/', 'shadow_runtime/', 'framework/', 'sandbox_runtime/')
PRODUCTION_WORDS = ('production pass', 'production-pass', 'production ready', 'production-ready', 'ready for production', 'ga ', 'general availability', '生产通过', '生产就绪', '生产可用', '可投入生产', '可上线')
HEX40 = re.compile(r'[0-9a-f]{40}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
FIELDS = {'schema', 'stage_id', 'candidate_sha', 'base_sha', 'scope', 'required_min_level', 'gates', 'claims', 'not_claimed', 'reviewed_by', 'manifest_sha256'}
GATE_FIELDS = {'id', 'command', 'exit_code', 'raw_log', 'raw_log_sha256', 'independence', 'status'}
CLAIM_FIELDS = {'id', 'statement', 'level', 'scope', 'gate_ids'}
REVIEW_FIELDS = {'implementer_id', 'reviewer_id', 'role', 'independent', 'session', 'window_start', 'window_end'}
HEADER_FIELDS = {'gate', 'command', 'exit_code'}
FAILURE_MARKERS = ('FAILED', 'ERROR:', 'FAIL:')
PRODUCTION_FIELDS = {'acceptance_status_path', 'acceptance_status_sha256', 'release_gate_path', 'release_gate_sha256'}


def canonical(body):
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def digest(body):
    return hashlib.sha256(canonical(body)).hexdigest()


def level_of(value):
    return LEVELS.get(value) if type(value) is str else None


def no_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError('duplicate key: ' + str(key))
        seen[key] = value
    return seen


def git(root, *args, text=True):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, text=text, encoding='utf-8' if text else None, errors=None if text else None, shell=False)


def committed_bytes(root, candidate, raw):
    result = subprocess.run(['git', 'cat-file', 'blob', candidate + ':' + raw], cwd=root, capture_output=True, shell=False)
    return result.stdout if result.returncode == 0 else None


def header_of(payload):
    first = payload.split(b'\n', 1)[0].decode('utf-8', 'replace')
    try:
        parsed = json.loads(first)
    except ValueError:
        return None
    if type(parsed) is not dict or set(parsed) != HEADER_FIELDS:
        return None
    return parsed


def check_evidence(gate, manifest, root, out, seen):
    gid = gate['id']
    raw = gate['raw_log']
    if type(raw) is not str or not raw or '\\' in raw or ':' in raw or '..' in pathlib.PurePosixPath(raw).parts:
        out.append(('gate_raw_path', gid))
        return
    if not raw.startswith(EVIDENCE_PREFIX) or raw.endswith('.json') or raw.startswith(FORBIDDEN_PREFIX):
        out.append(('gate_raw_path', gid))
        return
    if raw in seen:
        out.append(('gate_raw_reused', gid))
        return
    seen.add(raw)
    target = root / raw
    if not target.is_file() or target.is_symlink():
        out.append(('gate_raw_missing', gid))
        return
    payload = committed_bytes(root, manifest['candidate_sha'], raw)
    if payload is None:
        out.append(('gate_raw_untracked', gid))
        return
    stored = gate['raw_log_sha256']
    if type(stored) is not str or HEX64.match(stored) is None or hashlib.sha256(payload).hexdigest() != stored:
        out.append(('gate_raw_sha', gid))
        return
    header = header_of(payload)
    if header is None:
        out.append(('evidence_header', gid))
        return
    if header['gate'] != gid or header['command'] != gate['command'] or header['exit_code'] != gate['exit_code']:
        out.append(('evidence_mismatch', gid))
        return
    body = payload.split(b'\n', 1)[1].decode('utf-8', 'replace') if b'\n' in payload else ''
    for marker in FAILURE_MARKERS:
        if marker in body:
            out.append(('evidence_failure_text', gid))
            break


def check_gates(manifest, root, out, requirements):
    gates = manifest['gates']
    if type(gates) is not list or not gates:
        out.append(('gates', 'gates must be a non-empty list'))
        return {}
    min_level = level_of(manifest['required_min_level'])
    levels = {}
    seen = set()
    for gate in gates:
        if type(gate) is not dict or set(gate) != GATE_FIELDS:
            out.append(('gate_schema', 'gate field set mismatch'))
            continue
        gid = gate['id']
        if type(gid) is not str or not gid:
            out.append(('gate_schema', 'gate id missing'))
            continue
        if gid in levels:
            out.append(('gate_duplicate', gid))
        lvl = level_of(gate['independence'])
        if lvl is None:
            out.append(('gate_independence', gid))
        else:
            levels[gid] = lvl
            if min_level is not None and lvl < min_level:
                out.append(('gate_level_too_low', gid))
        if gate['status'] != 'PASS':
            out.append(('gate_not_run', gid))
        if type(gate['exit_code']) is not int or gate['exit_code'] != 0:
            out.append(('gate_exit', gid))
        if type(gate['command']) is not str or not gate['command'].strip():
            out.append(('gate_command', gid))
        check_evidence(gate, manifest, root, out, seen)
    required = requirements.get('required_gate_ids')
    if type(required) is not list or not required or not all(type(x) is str and x for x in required):
        out.append(('requirements_error', 'required_gate_ids must be non-empty strings'))
    else:
        for gid in sorted(set(required) - set(levels)):
            out.append(('gate_missing', gid))
        for gid in sorted(set(levels) - set(required)):
            out.append(('gate_extra', gid))
    required_level = requirements.get('min_level')
    if required_level is not None and required_level != manifest['required_min_level']:
        out.append(('requirements_mismatch', 'min_level'))
    return levels


def check_claims(manifest, out, levels):
    claims = manifest['claims']
    if type(claims) is not list or not claims:
        out.append(('claims', 'claims must be non-empty'))
        return
    min_level = level_of(manifest['required_min_level'])
    seen = set()
    for claim in claims:
        if type(claim) is not dict or set(claim) != CLAIM_FIELDS:
            out.append(('claim_schema', 'claim field set mismatch'))
            continue
        cid = claim['id']
        if type(cid) is not str or not cid:
            out.append(('claim_schema', 'claim id missing'))
            continue
        if cid in seen:
            out.append(('claim_duplicate', cid))
        seen.add(cid)
        statement = claim['statement']
        if type(statement) is not str or not statement.strip():
            out.append(('claim_statement', cid))
        else:
            lowered = statement.lower()
            for word in PRODUCTION_WORDS:
                if word in lowered:
                    out.append(('claim_production_wording', cid))
                    break
        lvl = level_of(claim['level'])
        if lvl is None:
            out.append(('claim_level', cid))
            continue
        if min_level is not None and lvl < min_level:
            out.append(('claim_level_too_low', cid))
        if claim['scope'] not in SCOPES:
            out.append(('claim_scope', cid))
        if claim['scope'] == 'production' and manifest['scope'] != 'production':
            out.append(('claim_scope_escalation', cid))
        ids = claim['gate_ids']
        if type(ids) is not list or not ids:
            out.append(('claim_gates', cid))
        else:
            for gid in ids:
                if gid not in levels:
                    out.append(('claim_unknown_gate', cid + ':' + str(gid)))
                elif levels[gid] < lvl:
                    out.append(('claim_level_exceeds_gate', cid + ':' + str(gid)))


def check_review(manifest, out):
    reviewer = manifest['reviewed_by']
    if type(reviewer) is not dict or set(reviewer) != REVIEW_FIELDS:
        out.append(('review_schema', 'reviewed_by field set mismatch'))
        return
    implementer = reviewer['implementer_id']
    verifier = reviewer['reviewer_id']
    if type(implementer) is not str or not implementer.strip() or type(verifier) is not str or not verifier.strip():
        out.append(('review_schema', 'reviewer ids must be non-empty strings'))
    elif implementer == verifier:
        out.append(('review_self_signed', 'reviewer equals implementer id'))
    if reviewer['role'] not in ROLES:
        out.append(('review_role', repr(reviewer['role'])))
    if reviewer['independent'] is not True:
        out.append(('review_not_independent', 'independent must be true'))
    if type(reviewer['session']) is not str or not reviewer['session'].strip():
        out.append(('review_session', 'session missing'))
    start = reviewer['window_start']
    end = reviewer['window_end']
    if type(start) is not str or type(end) is not str or not start.strip() or not end.strip() or not start < end:
        out.append(('review_window', 'window_start must precede window_end'))


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=no_duplicates)


def check_production(manifest, root, out):
    if manifest['scope'] != 'production':
        return
    evidence = manifest.get('production_evidence')
    if type(evidence) is not dict or set(evidence) != PRODUCTION_FIELDS:
        out.append(('production_unbound', 'production scope requires production_evidence'))
        return
    for key_path, key_sha in (('acceptance_status_path', 'acceptance_status_sha256'), ('release_gate_path', 'release_gate_sha256')):
        raw = evidence[key_path]
        if type(raw) is not str or not raw or raw.startswith('/') or '..' in pathlib.PurePosixPath(raw).parts:
            out.append(('production_unbound', key_path))
            return
        path = root / raw
        if not path.is_file():
            out.append(('production_unbound', 'missing ' + raw))
            return
        if hashlib.sha256(path.read_bytes()).hexdigest() != evidence[key_sha]:
            out.append(('production_unbound', 'digest mismatch ' + raw))
            return
    try:
        gate_state = read_json(root / evidence['release_gate_path'])
        acceptance = read_json(root / evidence['acceptance_status_path'])
    except (OSError, ValueError) as error:
        out.append(('production_unbound', 'unreadable evidence: ' + str(error)))
        return
    if type(gate_state) is not dict or gate_state.get('production', {}).get('state') != 'PASS':
        out.append(('production_unbound', 'release gate is not PASS'))
    if type(acceptance) is not dict or acceptance.get('production') != 'PASS':
        out.append(('production_unbound', 'acceptance status is not PASS'))


def committed_json(root, rev, path):
    payload = committed_bytes(root, rev, path)
    if payload is None:
        return None, None
    try:
        parsed = json.loads(payload.decode('utf-8'), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, ValueError):
        return None, payload
    return parsed, payload


def check_pins(manifest, root, pins, out):
    requirements, payload = committed_json(root, manifest['base_sha'], 'requirements.json')
    if payload is None:
        out.append(('requirements_uncommitted', 'base:requirements.json'))
        return None
    pinned = pins.get('requirements_sha256')
    if type(pinned) is not str or hashlib.sha256(payload).hexdigest() != pinned:
        out.append(('requirements_unpinned', 'digest does not match external pin'))
    if type(requirements) is not dict:
        out.append(('requirements_error', 'committed requirements must be an object'))
        return None
    manifest_pin = pins.get('manifest_sha256')
    if type(manifest_pin) is not str or type(manifest['manifest_sha256']) is not str or manifest_pin != manifest['manifest_sha256']:
        out.append(('manifest_unpinned', 'manifest digest must be pinned externally'))
    ref = pins.get('require_ref')
    if ref:
        if git(root, 'rev-parse', '--verify', ref).returncode != 0:
            out.append(('anchor_ref_missing', ref))
        elif git(root, 'merge-base', '--is-ancestor', manifest['candidate_sha'], ref).returncode != 0:
            out.append(('anchor_not_contained', ref))
    else:
        out.append(('anchor_ref_missing', 'no external ref pinned'))
    return requirements


def check_window(manifest, root, out):
    reviewer = manifest['reviewed_by']
    if type(reviewer) is not dict:
        return
    start = reviewer.get('window_start')
    end = reviewer.get('window_end')
    try:
        start_at = datetime.datetime.fromisoformat(str(start).replace('Z', '+00:00'))
        end_at = datetime.datetime.fromisoformat(str(end).replace('Z', '+00:00'))
    except ValueError:
        out.append(('review_window_format', 'ISO-8601 required'))
        return
    commit_time = git(root, 'show', '-s', '--format=%cI', manifest['candidate_sha']).stdout.strip()
    try:
        committed_at = datetime.datetime.fromisoformat(commit_time)
    except ValueError:
        return
    if start_at < committed_at:
        out.append(('review_window_early', 'window starts before candidate commit'))
    if end_at.tzinfo is not None and end_at > datetime.datetime.now(datetime.timezone.utc):
        out.append(('review_window_future', 'window ends after validation time'))

def validate(manifest, root, pins):
    if type(manifest) is not dict:
        return [('schema', 'manifest must be an object')]
    expected = FIELDS | ({'production_evidence'} if 'production_evidence' in manifest else set())
    if set(manifest) != expected:
        return [('schema', 'field set mismatch ' + repr(sorted(set(manifest) ^ expected)))]
    out = []
    body = {key: value for key, value in manifest.items() if key != 'manifest_sha256'}
    if type(manifest['manifest_sha256']) is not str or digest(body) != manifest['manifest_sha256']:
        out.append(('manifest_digest', 'manifest digest mismatch'))
    if manifest['schema'] != 'stage-manifest/3':
        out.append(('schema_version', repr(manifest['schema'])))
    if type(manifest['stage_id']) is not str or not manifest['stage_id'].strip():
        out.append(('stage_id', 'missing stage id'))
    for key in ('candidate_sha', 'base_sha'):
        value = manifest[key]
        if type(value) is not str or HEX40.match(value) is None:
            out.append(('commit_id', key + ' is not a 40-hex commit'))
    if manifest['candidate_sha'] == manifest['base_sha']:
        out.append(('commit_id', 'candidate equals base'))
    if manifest['scope'] not in SCOPES:
        out.append(('scope', repr(manifest['scope'])))
    if level_of(manifest['required_min_level']) is None:
        out.append(('required_min_level', repr(manifest['required_min_level'])))
    if git(root, 'cat-file', '-e', manifest['candidate_sha'] + '^{commit}').returncode != 0:
        out.append(('git_candidate_missing', manifest['candidate_sha']))
    elif git(root, 'merge-base', '--is-ancestor', manifest['base_sha'], manifest['candidate_sha']).returncode != 0:
        out.append(('git_base_not_ancestor', manifest['base_sha']))
    requirements = check_pins(manifest, root, pins, out)
    levels = check_gates(manifest, root, out, requirements or {})
    check_claims(manifest, out, levels)
    check_review(manifest, out)
    check_window(manifest, root, out)
    check_production(manifest, root, out)
    not_claimed = manifest['not_claimed']
    if type(not_claimed) is not list or not all(type(x) is str and x for x in not_claimed):
        out.append(('not_claimed_schema', 'not_claimed must be a list of strings'))
    elif manifest['scope'] == 'isolated':
        for needed in ('production', 'm6-migration'):
            if needed not in not_claimed:
                out.append(('not_claimed_missing', needed))
    return out


def build_manifest(body):
    manifest = dict(body)
    manifest['manifest_sha256'] = digest(body)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--pin-manifest-sha256', default='')
    parser.add_argument('--pin-requirements-sha256', default='')
    parser.add_argument('--require-ref', default='')
    args = parser.parse_args(argv)
    path = pathlib.Path(args.manifest)
    root = path.parent
    try:
        manifest = read_json(path)
    except (OSError, ValueError) as error:
        print('FAIL validator_error:', error)
        return 2
    pins = {'manifest_sha256': args.pin_manifest_sha256,
            'requirements_sha256': args.pin_requirements_sha256,
            'require_ref': args.require_ref}
    failures = validate(manifest, root, pins)
    for code, detail in failures:
        print('FAIL', code + ':', detail)
    print('STAGE MANIFEST:', 'PASS' if not failures else 'FAIL')
    print('CHECKS RUN: schema,digest,commits,pins,anchor,gates,evidence,requirements,claims,review,window,production,not_claimed')
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main())