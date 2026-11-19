"""Paired top-four retrieval on the frozen C4 normal cases. No production inputs."""
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framework.spec import parse
from sandbox_runtime.benchmark import build, run_case, sha
from sandbox_runtime.retrieval import PrivateBM25Store
from sandbox_runtime.store import Probe


def collect():
    manifest = parse((ROOT / 'spec/benchmark_cases.json').read_text(encoding='utf-8'))
    lock = parse((ROOT / 'spec/benchmark.lock.json').read_text(encoding='utf-8'))
    if sha(manifest) != lock['manifest_sha']:
        raise ValueError('manifest drift')
    rows = []
    for case in manifest['cases']:
        if case['variant'] != 'normal':
            continue
        old = run_case(case)
        if old['errors']:
            raise ValueError((case['id'], old['errors']))
        fixture, ctx, task = build(case)
        # Do not pass the known target, requirement key, seed or expected answer to search.
        store = PrivateBM25Store(fixture, synthetic=True, probe=Probe())
        hits = store.search_bm25(task['query'], ctx, 1, limit=4)
        exp = case['expected']
        locator = dict(id=exp['id'], revision=1, content_sha=hashlib.sha256(exp['body'].encode('utf-8')).hexdigest())
        ids = [hit['id'] for hit in hits]
        if len(set(ids)) != len(ids) or len(ids) > 4:
            raise ValueError('invalid top four')
        rows.append(dict(case=case['id'], query=case['query'], noise=case['noise'], seed=case['seed'],
                         fixture_sha=old['fixture_sha'], lexical_ids=old['text_top4'], lexical_hit=old['text_target_hit'],
                         bm25_locators=hits, bm25_hit=locator in hits, keyed_evidence=old['output']['status']=='ready'))
    groups = []
    for query, noise in sorted({(r['query'], r['noise']) for r in rows}):
        group = [r for r in rows if (r['query'],r['noise'])==(query,noise)]
        if sorted(r['seed'] for r in group) != [7,29]:
            raise ValueError('unpaired seeds')
        groups.append(dict(query=query,noise=noise,n=len(group),**{k:sum(int(r[k]) for r in group) for k in ('lexical_hit','bm25_hit','keyed_evidence')}))
    if len(groups)!=12 or len(rows)!=24:
        raise ValueError('incomplete matrix')
    return dict(manifest_sha=lock['manifest_sha'],ranked_fields=['body','key'],top_k=4,groups=groups,rows=rows,
                llm_evaluation='NOT_RUN',production='NOT_RUN')


if __name__=='__main__':
    print(json.dumps(collect(), ensure_ascii=True, sort_keys=True))
