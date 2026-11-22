"""Validate a stage evidence manifest for the self-verification protocol (stage-0.1).

Read-only: never writes acceptance status, release gates or production records.
"""
import argparse
import hashlib
import json
import pathlib
import re

LEVELS = {'I0': 0, 'I1': 1, 'I2': 2, 'I3': 3, 'I4': 4}
SCOPES = ('isolated', 'production')
FIELDS = {'schema', 'stage_id', 'candidate_sha', 'base_sha', 'scope', 'claims', 'required_gates', 'not_claimed', 'reviewed_by'}
GATE_FIELDS = {'id', 'command', 'exit_code', 'raw_log', 'raw_log_sha256', 'independence', 'status'}
CLAIM_FIELDS = {'id', 'statement', 'level', 'scope', 'gate_ids'}
REVIEW_FIELDS = {'role', 'implementer', 'independent'}
PRODUCTION_WORDS = ('production pass', 'production-pass', 'production ready', '生产通过', '可投入生产')
HEX40 = re.compile(r'[0-9a-f]{40}')
HEX64 = re.compile(r'[0-9a-f]{64}')


def _level(value):
    return LEVELS.get(value) if type(value) is str else None


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _gate_block(manifest, root, out):
    gates = manifest['required_gates']
    if type(gates) is not list or not gates:
        out.append(('gates', 'required_gates must be a non-empty list'))
        return {}
    levels = {}
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
        lvl = _level(gate['independence'])
        if lvl is None:
            out.append(('gate_independence', gid))
        else:
            levels[gid] = lvl
        if gate['status'] != 'PASS':
            out.append(('gate_not_run', gid + ' status ' + repr(gate['status'])))
        if type(gate['exit_code']) is not int or gate['exit_code'] != 0:
            out.append(('gate_exit', gid))
        if type(gate['command']) is not str or not gate['command'].strip():
            out.append(('gate_command', gid))
        raw = gate['raw_log']
        if type(raw) is not str or not raw or raw.startswith('/') or '..' in pathlib.PurePosixPath(raw).parts:
            out.append(('gate_raw_path', gid))
            continue
        if raw == 'spec/acceptance.status.json':
            out.append(('gate_readonly_status', gid))
            continue
        path = root / raw
        if not path.is_file():
            out.append(('gate_raw_missing', gid))
            continue
        if HEX64.fullmatch(gate['raw_log_sha256'] or '') is None or _sha(path) != gate['raw_log_sha256']:
            out.append(('gate_raw_sha', gid))
    return levels


def validate(manifest, root):
    out = []
    if type(manifest) is not dict:
        return [('schema', 'manifest must be an object')]
    if set(manifest) != FIELDS:
        return [('schema', 'field set mismatch ' + repr(sorted(set(manifest) ^ FIELDS)))]
    if manifest['schema'] != 'stage-manifest/1':
        out.append(('schema_version', repr(manifest['schema'])))
    stage = manifest['stage_id']
    if type(stage) is not str or not stage.strip():
        out.append(('stage_id', 'missing stage id'))
    for key in ('candidate_sha', 'base_sha'):
        value = manifest[key]
        if type(value) is not str or HEX40.fullmatch(value) is None:
            out.append(('commit_id', key + ' is not a 40-hex commit'))
    if manifest['candidate_sha'] == manifest['base_sha']:
        out.append(('commit_id', 'candidate equals base'))
    scope = manifest['scope']
    if scope not in SCOPES:
        out.append(('scope', 'unknown scope ' + repr(scope)))
    levels = _gate_block(manifest, root, out)
    claims = manifest['claims']
    if type(claims) is not list or not claims:
        out.append(('claims', 'claims must be non-empty'))
        claims = []
    for claim in claims:
        if type(claim) is not dict or set(claim) != CLAIM_FIELDS:
            out.append(('claim_schema', 'claim field set mismatch'))
            continue
        cid = str(claim['id'])
        lvl = _level(claim['level'])
        if lvl is None:
            out.append(('claim_level', cid))
            continue
        if claim['scope'] not in SCOPES:
            out.append(('claim_scope', cid))
        if claim['scope'] == 'production' and scope == 'isolated':
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
        if scope == 'isolated':
            text = claim['statement'] if type(claim['statement']) is str else ''
            low = text.lower()
            for word in PRODUCTION_WORDS:
                if word in low:
                    out.append(('claim_production_wording', cid))
                    break
    reviewer = manifest['reviewed_by']
    if type(reviewer) is not dict or set(reviewer) != REVIEW_FIELDS:
        out.append(('review_schema', 'reviewed_by field set mismatch'))
    else:
        if reviewer['implementer'] is not False:
            out.append(('review_self_signed', 'reviewer is the implementer'))
        if reviewer['independent'] is not True:
            out.append(('review_not_independent', 'reviewer is not independent'))
        if type(reviewer['role']) is not str or not reviewer['role'].strip():
            out.append(('review_role', 'role missing'))
    not_claimed = manifest['not_claimed']
    if type(not_claimed) is not list or not all(type(x) is str and x for x in not_claimed):
        out.append(('not_claimed_schema', 'not_claimed must be a list of strings'))
    elif scope == 'isolated':
        for needed in ('production', 'm6-migration'):
            if needed not in not_claimed:
                out.append(('not_claimed_missing', needed))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--root', default=None)
    args = parser.parse_args(argv)
    path = pathlib.Path(args.manifest)
    root = pathlib.Path(args.root) if args.root else path.parent
    try:
        manifest = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        print('FAIL manifest_read:', error)
        return 1
    failures = validate(manifest, root)
    for code, detail in failures:
        print('FAIL', code + ':', detail)
    print('STAGE MANIFEST:', 'PASS' if not failures else 'FAIL')
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main())