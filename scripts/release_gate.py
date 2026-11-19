"""Read-only qualification, never a deployer. Evidence producer and reviewer are trusted externally."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framework.spec import parse

PROFILES = ('production', 'power')
IDS = tuple(f'C{i:02}' for i in range(1, 11)) + tuple(f'R{i:02}' for i in range(1, 10))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def hexid(value, size):
    return type(value) is str and re.fullmatch(f'[0-9a-f]{{{size}}}', value) is not None


def fields(value, keys):
    return type(value) is dict and set(value) == set(keys.split())


def nonblank(value):
    return type(value) is str and bool(value.strip())


def check_artifact(directory, digest, ident, candidate):
    require(hexid(digest, 64), 'invalid evidence digest: '+ident)
    raw = (directory / (digest+'.json')).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest, 'evidence bytes changed: '+ident)
    obj = parse(raw.decode('utf-8'))
    require(fields(obj, 'id candidate scope data_sha policy_sha producer reviewer runs'), 'invalid evidence: '+ident)
    require(obj['id']==ident and obj['candidate']==candidate, 'wrong evidence target: '+ident)
    scope = 'specification' if ident.startswith('C') else ('production-power' if ident=='R04' else 'production')
    require(obj['scope']==scope, 'wrong evidence environment: '+ident)
    require(hexid(obj['data_sha'],64) and hexid(obj['policy_sha'],64), 'missing snapshot digests')
    require(nonblank(obj['producer']) and nonblank(obj['reviewer']) and obj['producer'].strip()!=obj['reviewer'].strip(), 'missing independent review')
    require(fields(obj['runs'], 'baseline injected restored'), 'missing controls')
    for phase, run in obj['runs'].items():
        require(fields(run, 'argv exit_code output') and type(run['argv']) is list and run['argv'] and all(nonblank(a) for a in run['argv']) and nonblank(run['output']), 'incomplete run: '+phase)
        require(type(run['exit_code']) is int and (run['exit_code']!=0 if phase=='injected' else run['exit_code']==0), 'bad control result: '+phase)


def evaluate(doc, directory, *, expected_candidate=None):
    require(fields(doc,'format candidate items release_markers') and type(doc['format']) is int and doc['format']==1, 'invalid register')
    candidate = doc['candidate']
    require(candidate is None or hexid(candidate,40), 'invalid candidate')
    if expected_candidate is not None:
        require(hexid(expected_candidate,40), 'invalid requested candidate')
        require(candidate is None or expected_candidate==candidate, 'wrong candidate')
    require(type(doc['items']) is dict and set(doc['items'])==set(IDS), 'missing or extra obligation')
    blockers = {p: [] for p in PROFILES}
    for ident in IDS:
        item = doc['items'][ident]
        required = ['power'] if ident=='R04' else list(PROFILES)
        require(fields(item,'state required_for evidence_sha') and item['required_for']==required, 'obligation changed: '+ident)
        state = item['state']
        require(state in ('PASS','FAIL','NOT_RUN'), 'bad state: '+ident)
        if state=='PASS':
            require(candidate is not None,'unbound PASS')
            check_artifact(directory,item['evidence_sha'],ident,candidate)
        else:
            require(item['evidence_sha'] is None, 'unexpected PASS artifact')
            for p in required:
                blockers[p].append(ident)
    markers = doc['release_markers']
    require(type(markers) is list and all(type(p) is str and p in PROFILES for p in markers) and len(set(markers))==len(markers),'invalid release markers')
    require(not any(blockers[p] for p in markers),'release marked with incomplete obligations')
    return {p:{'state':'BLOCK' if blockers[p] else 'ELIGIBLE', 'missing_pass':blockers[p]} for p in PROFILES}


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--profile',choices=PROFILES,help='require eligibility rather than check register consistency')
    cli.add_argument('--candidate',help='independently selected candidate commit')
    cli.add_argument('--status',type=Path,default=ROOT/'spec/acceptance.status.json')
    cli.add_argument('--evidence-dir',type=Path,default=ROOT/'docs/release-evidence')
    args=cli.parse_args()
    if bool(args.profile)!=bool(args.candidate): cli.error('supply profile and candidate together')
    try:
        results=evaluate(parse(args.status.read_text(encoding='utf-8')),args.evidence_dir,expected_candidate=args.candidate)
        print(json.dumps(results,sort_keys=True))
        return 3 if args.profile and results[args.profile]['state']!='ELIGIBLE' else 0
    except (OSError,ValueError,TypeError,RecursionError) as e:
        print('INVALID:',e,file=sys.stderr); return 2

if __name__=='__main__':
    raise SystemExit(main())
