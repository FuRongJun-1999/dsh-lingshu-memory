"""授权候选排序，不交付正文，也不持有存储。"""
from dataclasses import dataclass

from framework.conditions import bitemporal_match, condition_match
from framework.contracts import build_untrusted_record, extract_condition_space, validate_v2_request
from framework.security import context_shape, integer
from framework.ranking import bm25_rank_visible, wordset


@dataclass(frozen=True)
class SearchPage:
    locators: tuple[dict, ...] = ()
    has_more: bool = False
    error: str | None = None


def read_search(request, *, context, now, view, postings, body, model, offset=0, rank_key=None):
    """只消费受信快照及索引；调用者必须在交付前复核当前权限和快照。"""
    req = validate_v2_request(request)
    if req['kind'] != 'Read.search':
        raise ValueError('READ_SEARCH_REQUIRED')
    if not integer(offset) or ('cursor' in req) != (offset > 0):
        raise ValueError('VALIDATED_CURSOR_OFFSET_REQUIRED')
    try:
        actor = context_shape(context)
    except (ValueError, TypeError, RecursionError):
        return SearchPage(error='AUTH_REQUIRED')
    if not integer(now) or now >= actor['expires_at']:
        return SearchPage(error='AUTH_REQUIRED')
    if view.policy_generation != actor['policy_generation']:
        return SearchPage(error='POLICY_CHANGED')
    if postings is None and view.nodes:
        return SearchPage(error='INTEGRITY_FAILURE')
    ids = set()
    for token in wordset(req['query']):
        ids.update((postings or {}).get(token, ()))
    condition = extract_condition_space(req['condition_query'])
    point = {req['time_axis']: req['time_point']}
    locators = {}
    # 先筛完，再读排名正文。被拒绝或条件未知时，不开始排名。
    for key in sorted(ids):
        if not model.can_read(key, view.nodes, tenant=actor['tenant'], principal=actor['principal'], clearance=actor['clearance']):
            continue
        meta = view.metadata[key]
        verdicts = condition_match(meta['condition_space'], condition), bitemporal_match(meta['bitemporal'], point)
        if 'NO_MATCH' in verdicts:
            continue
        if 'DEFER' in verdicts:
            return SearchPage(error='CONDITION_DEFERRED')
        node = view.nodes[key]
        locators[key] = dict(id=key, revision=node.revision, content_sha=node.content_sha)
    pool = {}
    try:
        for key, locator in locators.items():
            text = body(key, locator['revision'])
            build_untrusted_record(locator, text)
            pool[key] = dict(body=text, key=key if rank_key is None else rank_key(key))
    except (OSError, ValueError):
        return SearchPage(error='INTEGRITY_FAILURE')
    ranked = bm25_rank_visible(list(pool), req['query'], pool, len(pool))
    end = offset + req['limit']
    return SearchPage(tuple(locators[key] for key in ranked[offset:end]), end < len(ranked))
