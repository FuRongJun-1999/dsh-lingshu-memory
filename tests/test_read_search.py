import hashlib
import unittest
from dataclasses import replace
from framework.contracts import extract_condition_space
from framework.migration import time_bundle
from framework.model import Model, Node
from framework.read_get import ReadSnapshot
from framework.read_search import read_search
from test_shadow_runtime import bitemp, cspace, ctx, Q


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.text = {'private':'blue', 'z-focus':'blue blue blue', 'a-noise':'blue long noise tail'}
        self.nodes = {k: Node('t1',1,hashlib.sha256(v.encode()).hexdigest(),1,
                              frozenset({'alice','bob'}),frozenset({'bob' if k=='private' else 'alice'}))
                      for k,v in self.text.items()}
        self.meta = {k: dict(condition_space=extract_condition_space(cspace()),bitemporal=time_bundle(bitemp())) for k in self.text}
        self.req = dict(kind='Read.search',query='blue',limit=1,include_provenance=False,
                        condition_query=cspace(),time_axis='effective',time_point=Q)
        self.reads = []

    def execute(self, req=None, **kw):
        def body(key,rev):
            self.reads.append(key)
            return self.text[key]
        args = dict(context=ctx(),now=10,view=ReadSnapshot(2,1,self.nodes,self.meta),
                    postings={'blue':list(self.nodes)},body=body,model=Model())
        return read_search(req or self.req, **dict(args,**kw))

    def test_authorization_precedes_scoring_and_limit(self):
        page = self.execute()
        self.assertEqual(page.locators, (dict(id='z-focus',revision=1,content_sha=self.nodes['z-focus'].content_sha),))
        self.assertTrue(page.has_more)
        self.assertEqual(self.reads,['a-noise','z-focus'])
        self.assertEqual([r['id'] for r in self.execute(dict(self.req,cursor='cursor-fixture'),offset=1).locators],['a-noise'])

    def test_no_relevant_or_applicable_record_does_not_read_body(self):
        self.assertEqual(self.execute(dict(self.req,query='different')).locators,())
        self.assertEqual(self.execute(dict(self.req,time_point='2024-01-10T00:00:00Z')).locators,())
        self.assertEqual(self.execute(dict(self.req,condition_query=dict(cspace(),method={'state':'unknown'}))).error,'CONDITION_DEFERRED')
        self.assertEqual(self.execute(postings=None).error,'INTEGRITY_FAILURE')
        self.assertEqual(self.execute(context=ctx(policy_generation=2)).error,'POLICY_CHANGED')
        self.assertEqual(self.execute(now=1000).error,'AUTH_REQUIRED')
        self.assertEqual(self.reads,[])

    def test_digest_mismatch_is_not_ranked(self):
        self.text['a-noise']='different bytes'
        self.assertEqual(self.execute().error,'INTEGRITY_FAILURE')

    def test_frozen_queries_candidate_order_matches_known_baseline(self):
        from framework.spec import ROOT, parse
        from sandbox_runtime.benchmark import build, sha
        from sandbox_runtime.retrieval import PrivateBM25Store
        from sandbox_runtime.store import Probe, wordset
        manifest = parse((ROOT/'spec/benchmark_cases.json').read_text(encoding='utf-8'))
        lock = parse((ROOT/'spec/benchmark.lock.json').read_text(encoding='utf-8'))
        self.assertEqual(sha(manifest),lock['manifest_sha'])
        condition = extract_condition_space(cspace())
        time = time_bundle(bitemp())
        n = 0
        for case in manifest['cases']:
            if case['variant'] != 'normal':
                continue
            n += 1
            rows, actor, task = build(case)
            self.assertEqual(sha(rows),case['fixture_sha'])
            # 使用原本的排序字段（知识键），避免把字段替换误报成算法差异。
            old = PrivateBM25Store(rows,synthetic=True,probe=Probe()).search_bm25(task['query'],actor,1,limit=4)
            texts, nodes, meta, posts, keys = {}, {}, {}, {}, {}
            for row in rows:
                nid = row['id']; text = row['body']; keys[nid] = row['key']; texts[nid] = text
                nodes[nid] = Node(row['tenant'],row['revision'],hashlib.sha256(text.encode()).hexdigest(),row['sensitivity'],frozenset(row['creation_readers']),frozenset(row['current_readers']))
                meta[nid] = dict(condition_space=condition,bitemporal=time)
                for token in wordset(text+' '+keys[nid]):
                    posts.setdefault(token, []).append(nid)
            req = dict(self.req, query=task['query'], limit=4)
            page = read_search(req,context=actor,now=1,view=ReadSnapshot(1,1,nodes,meta),postings=posts,
                               body=lambda key,rev:texts[key],rank_key=keys.__getitem__,model=Model())
            self.assertIsNone(page.error); self.assertEqual(list(page.locators),old,case['id'])
        self.assertEqual(n,24)

    def test_order_and_visibility_faults_have_observable_counterexamples(self):
        from pathlib import Path
        import sys
        from types import ModuleType
        from unittest.mock import patch
        filename = read_search.__code__.co_filename
        src = Path(filename).read_text(encoding='utf-8')
        # 仅改变两个实际功能点；正常代码须先对同一输入给出正确结果。
        good = self.execute(); self.assertEqual(good.locators[0]['id'],'z-focus')
        self.assertEqual(self.reads,['a-noise','z-focus'])
        original_guard = "        if not model.can_read(key, view.nodes, tenant=actor['tenant'], principal=actor['principal'], clearance=actor['clearance']):"
        original_rank = "    ranked = bm25_rank_visible(list(pool), req['query'], pool, len(pool))"
        for old, new, expected in [(original_guard, '        if False:', 'private_body_read'),
                                    (original_rank,'    ranked = sorted(pool)', 'wrong_rank')]:
            with self.subTest(observation=expected):
                self.reads.clear(); self.assertEqual(src.count(old),1)
                mod = ModuleType('_search_single_fault')
                with patch.dict(sys.modules, {mod.__name__:mod}):
                    exec(compile(src.replace(old,new,1),filename,'exec'),mod.__dict__)
                    with patch.dict(globals(),read_search=mod.read_search):
                        changed = self.execute()
                self.assertEqual(('private' in self.reads,changed.locators[0]['id']=='a-noise'),
                                 (True,False) if expected=='private_body_read' else (False,True))
