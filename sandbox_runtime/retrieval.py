"""Private-pool Okapi BM25 ranker (strictly post-authorization; never leaks hidden stats)."""
from __future__ import annotations
import re
from sandbox_runtime.store import SyntheticStore
from framework.ranking import bm25_rank_visible, doc_terms


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
