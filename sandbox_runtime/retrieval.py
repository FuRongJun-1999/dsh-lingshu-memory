"""Private-pool Okapi BM25 ranker (strictly post-authorization; never leaks hidden stats)."""
from __future__ import annotations
import math
import re
from sandbox_runtime.store import SyntheticStore


def doc_terms(record: dict) -> list[str]:
    text_val = record["body"] + " " + record.get("key", "")
    return re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]", text_val.lower())


def bm25_rank_visible(visible_keys: list[str], query: str, records: dict[str, dict], limit: int,
                      *, k1: float = 1.5, b: float = 0.75) -> list[str]:
    """Compute Okapi BM25 strictly inside already-authorized visible_keys."""
    n_docs = len(visible_keys)
    if n_docs == 0 or limit <= 0:
        return []
    q_tokens = frozenset(re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]", query.lower()))
    docs = {k: doc_terms(records[k]) for k in visible_keys}
    avgdl = sum(len(t) for t in docs.values()) / n_docs
    if avgdl <= 0:
        return sorted(visible_keys)[:limit]
    df = {t: sum(1 for terms in docs.values() if t in terms) for t in q_tokens}
    scores = {}
    for k, terms in docs.items():
        dl = len(terms)
        tf_map: dict[str, int] = {}
        for t in terms:
            tf_map[t] = tf_map.get(t, 0) + 1
        score = 0.0
        for t in q_tokens:
            tf = tf_map.get(t, 0)
            if tf == 0:
                continue
            idf = math.log((n_docs - df[t] + 0.5) / (df[t] + 0.5) + 1.0)
            denom = tf + k1 * (1.0 - b + b * (dl / avgdl))
            score += idf * ((tf * (k1 + 1.0)) / denom)
        scores[k] = round(score, 12)
    return sorted(visible_keys, key=lambda key: (-scores[key], key))[:limit]


class PrivateBM25Store:
    """Wrapper over SyntheticStore adding post-auth BM25 ranking without mutating frozen store.py."""

    def __init__(self, fixture, *, synthetic: bool, probe):
        self._store = SyntheticStore(fixture, synthetic=synthetic, probe=probe)

    def search_bm25(self, query: str, context: dict, now: int, *, limit: int = 8, request_id=None):
        # Retrieve all authorized candidate locators via SyntheticStore._allowed first
        ctx = self._store._context(context, now)
        tokens = frozenset(re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]", query.lower()))
        ids = set().union(*(self._store._tokens.get(t, ()) for t in tokens))
        visible = [key for key in ids if self._store._allowed(key, ctx)]
        ranked = bm25_rank_visible(visible, query, self._store._records, limit)
        result = [
            {"id": k, "revision": self._store._nodes[k].revision, "content_sha": self._store._nodes[k].content_sha}
            for k in ranked
        ]
        self._store._trace("search", query, {"ranking": "bm25", "limit": limit}, result, request_id, returned=len(result), mode="bm25")
        return result
