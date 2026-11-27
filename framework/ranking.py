"""可见候选池内的确定性排序，不访问存储。"""
import math
import re


def wordset(text):
    return frozenset(re.findall(r"[a-z0-9_]+|[㐀-鿿]", text.lower()))


def doc_terms(record: dict) -> list[str]:
    text_val = record["body"] + " " + record.get("key", "")
    return re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]", text_val.lower())


def bm25_rank_visible(visible_keys: list[str], query: str, records: dict[str, dict], limit: int,
                      *, k1: float = 1.5, b: float = 0.75) -> list[str]:
    """Compute Okapi BM25 strictly inside already-authorized visible_keys."""
    n_docs = len(visible_keys)
    if n_docs == 0 or limit <= 0:
        return []
    q_tokens = sorted(set(re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]", query.lower())))
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
