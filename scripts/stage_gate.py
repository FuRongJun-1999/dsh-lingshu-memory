"""Validate a stage evidence manifest (self-verification protocol, schema v3).

Read-only. Evidence is anchored to committed bytes; the validator never writes
acceptance status, release gates or production records."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
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
REVIEW_FIELDS = {'implementer_id', 'reviewer_id', 'role', 'independent', 'session', 'window_start', 'window_end', 'reviewer_keyid', 'signature'}
HEADER_FIELDS = {'gate', 'command', 'exit_code'}
FAILURE_MARKERS = ('failed', 'fail', 'error', 'traceback', 'exit status 1', 'exit status 2', 'exit status 3', 'err!')
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


GIT_ENV = {'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull}


def git(root, *args, text=True):
    env = dict(os.environ, **GIT_ENV)
    return subprocess.run(['git', '--no-replace-objects', '-c', 'core.fsmonitor=false',
                           '-c', 'core.hooksPath=' + os.devnull, *args], cwd=root, capture_output=True,
                          text=text, encoding='utf-8' if text else None, env=env, shell=False)


def committed_bytes(root, candidate, raw):
    env = dict(os.environ, **GIT_ENV)
    result = subprocess.run(['git', '--no-replace-objects', 'cat-file', 'blob', candidate + ':' + raw],
                            cwd=root, capture_output=True, env=env, shell=False)
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
    lowered_body = body.lower()
    for marker in FAILURE_MARKERS:
        if marker in lowered_body:
            out.append(('evidence_failure_text', gid))
            break
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines or lines[-1] != 'RESULT: PASS gate=' + gid + ' exit=0':
        out.append(('evidence_result_missing', gid))


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


def review_payload(manifest):
    body = {key: value for key, value in manifest.items() if key != 'manifest_sha256'}
    reviewed = {key: value for key, value in body['reviewed_by'].items() if key != 'signature'}
    body['reviewed_by'] = reviewed
    return canonical(body)

def check_review(manifest, pins, out, performed):
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
    keys = [str(item).lower() for item in (pins.get('reviewer_keys') or [])]
    keyid = reviewer['reviewer_keyid']
    if type(keyid) is not str or HEX64.match(keyid.lower()) is None or keyid.lower() not in keys:
        out.append(('review_key_untrusted', repr(keyid)))
        return
    signature = reviewer['signature']
    if type(signature) is not str or re.fullmatch(r'[0-9a-f]{128}', signature.lower()) is None:
        out.append(('review_bad_signature', 'signature must be 128 hex characters'))
        return
    try:
        verifier = ed25519_module()
        review_valid = verifier.verify(bytes.fromhex(keyid), review_payload(manifest), bytes.fromhex(signature))
    except Exception as error:
        out.append(('review_bad_signature', 'verification failed: ' + str(error)))
        return
    performed.append('review-signature')
    if not review_valid:
        out.append(('review_bad_signature', 'reviewer signature does not verify'))


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=no_duplicates)


def production_path_ok(raw):
    if type(raw) is not str or not raw or '\\' in raw or ':' in raw:
        return False
    parts = pathlib.PurePosixPath(raw).parts
    return bool(parts) and '..' not in parts and not raw.startswith('/')


def check_production(manifest, root, out):
    if manifest['scope'] != 'production':
        return
    evidence = manifest.get('production_evidence')
    if type(evidence) is not dict or set(evidence) != PRODUCTION_FIELDS:
        out.append(('production_unbound', 'production scope requires production_evidence'))
        return
    for key_path, key_sha in (('acceptance_status_path', 'acceptance_status_sha256'), ('release_gate_path', 'release_gate_sha256')):
        raw = evidence[key_path]
        if not production_path_ok(raw):
            out.append(('production_path_invalid', str(raw)))
            return
    blobs = {}
    for key_path, key_sha in (('acceptance_status_path', 'acceptance_status_sha256'), ('release_gate_path', 'release_gate_sha256')):
        raw = evidence[key_path]
        payload = committed_bytes(root, manifest['candidate_sha'], raw)
        if payload is None:
            out.append(('production_uncommitted', raw))
            return
        if hashlib.sha256(payload).hexdigest() != evidence[key_sha]:
            out.append(('production_unbound', 'digest mismatch ' + raw))
            return
        blobs[raw] = payload
    gate_state = None
    acceptance = None
    try:
        gate_state = json.loads(blobs[evidence['release_gate_path']].decode('utf-8'), object_pairs_hook=no_duplicates)
        acceptance = json.loads(blobs[evidence['acceptance_status_path']].decode('utf-8'), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, ValueError):
        out.append(('production_malformed', 'committed evidence is not valid json'))
        return
    if type(gate_state) is not dict or type(gate_state.get('production')) is not dict:
        out.append(('production_malformed', 'release gate shape'))
        return
    if type(acceptance) is not dict:
        out.append(('production_malformed', 'acceptance shape'))
        return
    if gate_state['production'].get('state') != 'PASS':
        out.append(('production_unbound', 'release gate is not PASS'))
    if acceptance.get('production') != 'PASS':
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


def ed25519_module():
    path = pathlib.Path(__file__).with_name('ed25519.py')
    spec = importlib.util.spec_from_file_location('_stage_ed25519', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ATTESTATION_FIELDS = {'manifest_sha256', 'requirements_sha256', 'ref', 'ref_sha', 'issuer', 'issued_at', 'public_key', 'signature'}


def check_attestation(manifest, pins, out):
    path = pins.get('attestation_path')
    trusted = [key.lower() for key in pins.get('trusted_keys') or []]
    if not path:
        if pins.get('allow_weak_pin'):
            return
        out.append(('attestation_missing', 'no signed attestation supplied'))
        return
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding='utf-8'), object_pairs_hook=no_duplicates)
    except (OSError, ValueError) as error:
        out.append(('attestation_schema', str(error)))
        return
    if type(data) is not dict or set(data) != ATTESTATION_FIELDS:
        out.append(('attestation_schema', 'field set mismatch'))
        return
    key = data['public_key']
    if type(key) is not str or HEX64.match(key.lower()) is None or key.lower() not in trusted:
        out.append(('attestation_untrusted_key', repr(key)))
        return
    signature = data['signature']
    if type(signature) is not str or re.fullmatch(r'[0-9a-f]{128}', signature.lower()) is None:
        out.append(('attestation_schema', 'signature must be 128 hex characters'))
        return
    body = {name: data[name] for name in ATTESTATION_FIELDS - {'signature'}}
    try:
        verifier = ed25519_module()
        attestation_valid = verifier.verify(bytes.fromhex(key), canonical(body), bytes.fromhex(signature))
    except Exception as error:
        out.append(('attestation_schema', 'verification failed: ' + str(error)))
        return
    if not attestation_valid:
        out.append(('attestation_bad_signature', 'signature does not verify'))
        return
    if data['manifest_sha256'] != manifest.get('manifest_sha256'):
        out.append(('attestation_mismatch', 'manifest_sha256'))
    if data['requirements_sha256'] != pins.get('requirements_sha256'):
        out.append(('attestation_mismatch', 'requirements_sha256'))
    if data['ref'] != pins.get('require_ref') or data['ref_sha'] != pins.get('ref_sha'):
        out.append(('attestation_mismatch', 'ref pin'))
    if type(data['issuer']) is not str or not data['issuer'].strip():
        out.append(('attestation_schema', 'issuer must be non-empty'))
    try:
        issued = datetime.datetime.fromisoformat(str(data['issued_at']).replace('Z', '+00:00'))
    except ValueError:
        out.append(('attestation_schema', 'issued_at must be ISO-8601'))
        return
    if issued.tzinfo is None:
        out.append(('attestation_schema', 'issued_at requires timezone'))
    elif issued > datetime.datetime.now(datetime.timezone.utc):
        out.append(('attestation_time', 'issued_at is in the future'))

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
    if type(ref) is not str or not ref.strip():
        out.append(('anchor_ref_missing', 'no external ref pinned'))
        return requirements
    if not ref.startswith(('refs/remotes/', 'refs/tags/')):
        out.append(('anchor_ref_invalid', repr(ref)))
        return requirements
    head = git(root, 'rev-parse', '--verify', ref)
    if head.returncode != 0:
        out.append(('anchor_ref_missing', ref))
        return requirements
    tip = head.stdout.strip()
    pin_ref = pins.get('ref_sha')
    if type(pin_ref) is not str or pin_ref != tip:
        out.append(('anchor_ref_moved', ref + ' -> ' + tip))
    if git(root, 'merge-base', '--is-ancestor', manifest['candidate_sha'], ref).returncode != 0:
        out.append(('anchor_not_contained', ref))
    if git(root, 'merge-base', '--is-ancestor', manifest['base_sha'], ref).returncode != 0:
        out.append(('anchor_base_outside_ref', manifest['base_sha']))
    for rev in (manifest['candidate_sha'], tip):
        other = committed_bytes(root, rev, 'requirements.json')
        if other is None or other != payload:
            out.append(('requirements_drift', rev))
            break
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
    if start_at.tzinfo is None or end_at.tzinfo is None:
        out.append(('review_window_naive', 'timezone offset required'))
        return
    commit_time = git(root, 'show', '-s', '--format=%cI', manifest['candidate_sha']).stdout.strip()
    try:
        committed_at = datetime.datetime.fromisoformat(commit_time)
    except ValueError:
        out.append(('review_window_unknown', 'candidate commit time unavailable'))
        return
    try:
        if start_at < committed_at:
            out.append(('review_window_early', 'window starts before candidate commit'))
    except TypeError:
        out.append(('review_window_compare', 'offset-naive and offset-aware cannot be compared'))
    if end_at.tzinfo is not None and end_at > datetime.datetime.now(datetime.timezone.utc):
        out.append(('review_window_future', 'window ends after validation time'))

def validate(manifest, root, pins, performed=None):
    if performed is None:
        performed = []
    if type(manifest) is not dict:
        return [('schema', 'manifest must be an object')]
    expected = FIELDS | ({'production_evidence'} if 'production_evidence' in manifest else set())
    if set(manifest) != expected:
        return [('schema', 'field set mismatch ' + repr(sorted(set(manifest) ^ expected)))]
    out = []
    performed.append('schema')
    body = {key: value for key, value in manifest.items() if key != 'manifest_sha256'}
    performed.append('digest')
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
    performed.append('commits')
    if git(root, 'cat-file', '-e', manifest['candidate_sha'] + '^{commit}').returncode != 0:
        out.append(('git_candidate_missing', manifest['candidate_sha']))
    elif git(root, 'merge-base', '--is-ancestor', manifest['base_sha'], manifest['candidate_sha']).returncode != 0:
        out.append(('git_base_not_ancestor', manifest['base_sha']))
    requirements = check_pins(manifest, root, pins, out)
    performed.extend(['pins', 'anchor'])
    check_attestation(manifest, pins, out)
    performed.append('attestation')
    levels = check_gates(manifest, root, out, requirements or {})
    performed.extend(['gates', 'evidence', 'result-line', 'requirements'])
    check_claims(manifest, out, levels)
    performed.append('claims')
    check_review(manifest, pins, out, performed)
    performed.append('review')
    check_window(manifest, root, out)
    performed.extend(['window', 'production'])
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
    parser.add_argument('--pin-ref-sha', default='')
    parser.add_argument('--attestation', default='')
    parser.add_argument('--trusted-key', action='append', default=[])
    parser.add_argument('--allow-weak-pin', action='store_true')
    parser.add_argument('--reviewer-key', action='append', default=[])
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
            'require_ref': args.require_ref,
            'ref_sha': args.pin_ref_sha,
            'attestation_path': args.attestation,
            'trusted_keys': args.trusted_key,
            'allow_weak_pin': args.allow_weak_pin,
            'reviewer_keys': args.reviewer_key}
    performed = []
    try:
        failures = validate(manifest, root, pins, performed)
    except Exception as error:
        print('FAIL validator_error:', error)
        return 2
    for code, detail in failures:
        print('FAIL', code + ':', detail)
    print('STAGE MANIFEST:', 'PASS' if not failures else 'FAIL')
    if args.allow_weak_pin and not args.attestation:
        print('WARNING weak_pin: running without a signed attestation')
    print('CHECKS RUN:', ','.join(dict.fromkeys(performed)))
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main())