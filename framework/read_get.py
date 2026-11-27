"""独立授权回读：不发现存储、不认证主体、不发送网络响应。"""
from dataclasses import dataclass
from collections.abc import Callable, Mapping
from typing import Any

from framework.conditions import bitemporal_match, condition_match
from framework.contracts import build_untrusted_record, extract_condition_space, validate_full_response, validate_v2_request
from framework.model import Model, Node
from framework.security import binding_shape, context_shape, emit_allowed
from framework.spec import digest


@dataclass(frozen=True)
class ReadSnapshot:
    content_generation: int
    policy_generation: int
    nodes: Mapping[str, Node]
    metadata: Mapping[str, dict]

    @property
    def id(self):
        return f"snap-{self.content_generation}-{self.policy_generation}"


def read_get(request: dict, *, context: dict, now: int, request_id: str,
             snapshot: Callable[[], ReadSnapshot],
             body: Callable[[str, int], str], model: Model,
             current_context: Callable[[], dict], current_now: Callable[[], int]) -> dict[str, Any]:
    """调用方在同一工作单元内提供受信快照、主体与时钟；正文读回不是授权。"""
    req = validate_v2_request(request)
    if req['kind'] != 'Read.get':
        raise ValueError('READ_GET_REQUIRED')
    base = dict(version='0.2-full', request_id=request_id, scope='read', next_cursor=None,
                target=None, historical_receipt=None, selfcheck_aggregate=None)

    def reject(code, action):
        return validate_full_response(dict(base, outcome='error', error_code=code, next_action=action,
                                           records=None, snapshot_ref=None, policy_generation=None))

    def changed():
        return reject('POLICY_CHANGED', 'refresh_snapshot')

    def allowed(view, key, actor):
        return model.can_read(key, view.nodes, tenant=actor['tenant'], principal=actor['principal'],
                              clearance=actor['clearance'])

    try:
        ctx = context_shape(context)
        if type(now) is not int or not 0 <= now < ctx['expires_at']:
            raise ValueError('AUTH_REQUIRED')
    except ValueError:
        return reject('AUTH_REQUIRED', 'authenticate')

    first = snapshot()
    if first.policy_generation != ctx['policy_generation']:
        return changed()
    key = req['node_id']
    if not allowed(first, key, ctx):
        return reject('NOT_FOUND_OR_DENIED', 'authenticate')

    selected = first.nodes[key]
    locator = dict(id=key, revision=selected.revision, content_sha=selected.content_sha)
    meta = first.metadata[key]
    cv = condition_match(meta['condition_space'], extract_condition_space(req['condition_query']))
    tv = bitemporal_match(meta['bitemporal'], {req['time_axis']: req['time_point']})
    records = []
    provenance = None
    if 'NO_MATCH' not in (cv, tv):
        if 'DEFER' in (cv, tv):
            return reject('CONDITION_DEFERRED', 'fix_input')
        if req['include_provenance']:
            provenance = dict(source_kind=meta['source_attribution']['source_kind'],
                              source_id=meta['source_attribution']['source_id'],
                              redacted_edges=sum(not allowed(first, e.target, ctx) for e in selected.edges))
        try:
            records.append(build_untrusted_record(locator, body(key, selected.revision), provenance))
        except (OSError, ValueError):
            return reject('INTEGRITY_FAILURE', 'refresh_snapshot')

    response = dict(base, outcome='ok', error_code=None, next_action='none', records=records,
                    snapshot_ref=first.id, policy_generation=first.policy_generation)
    query_sha, response_sha = digest(req), digest(response)

    def binding(view, actor):
        return binding_shape(dict(context=actor, snapshot=dict(id=view.id,
            content_generation=view.content_generation, policy_generation=view.policy_generation,
            expires_at=actor['expires_at']), read_kind='Read.get', query_sha=query_sha,
            response_sha=response_sha, cursor_sha=None))

    prepared = binding(first, ctx)
    fresh = snapshot()
    try:
        actor, clock = context_shape(current_context()), current_now()
        live = binding(fresh, actor)
    except (ValueError, TypeError, RecursionError):
        return changed()
    node = fresh.nodes.get(key)
    reauthorized = allowed(fresh, key, actor) and (node.revision, node.content_sha) == (locator['revision'], locator['content_sha'])
    if provenance is not None and reauthorized:
        live_source = fresh.metadata[key]['source_attribution']
        reauthorized = (all(live_source[k] == provenance[k] for k in ('source_kind','source_id'))
                        and sum(not allowed(fresh, e.target, actor) for e in node.edges) == provenance['redacted_edges'])
    reauthorized = reauthorized and all(
        fresh.metadata[key][field] == meta[field] for field in ("condition_space", "bitemporal")
    )
    if not emit_allowed(prepared, live, clock, True, reauthorized, True):
        return changed()
    return validate_full_response(response)
