"""授权的当前修订验证态；不提供全库统计或证明正文。"""
from framework.conditions import bitemporal_match, condition_match
from framework.contracts import extract_condition_space, validate_v2_request
from framework.security import context_shape, integer
from framework.verification import proof_applies


def read_status(request, *, context, now, view, model, proof):
    """使用 Read.get 的只读选择条件。调用者在同锁下提供已校验快照及证明读口。"""
    req = validate_v2_request(request)
    if req['kind'] != 'Read.get' or req['include_provenance']:
        raise ValueError('STATUS_SELECTOR_REQUIRED')
    try:
        actor = context_shape(context)
    except (ValueError, TypeError, RecursionError):
        return {'error': 'AUTH_REQUIRED'}
    if not integer(now) or now >= actor['expires_at']:
        return {'error': 'AUTH_REQUIRED'}
    if view.policy_generation != actor['policy_generation']:
        return {'error': 'POLICY_CHANGED'}
    key = req['node_id']
    if not model.can_read(key, view.nodes, tenant=actor['tenant'], principal=actor['principal'], clearance=actor['clearance']):
        return {'error': 'NOT_FOUND_OR_DENIED'}
    node, meta = view.nodes[key], view.metadata[key]
    checks = (condition_match(meta['condition_space'], extract_condition_space(req['condition_query'])),
              bitemporal_match(meta['bitemporal'], {req['time_axis']: req['time_point']}))
    if 'NO_MATCH' in checks:
        return {'status': 'not_applicable'}
    if 'DEFER' in checks:
        return {'error': 'CONDITION_DEFERRED'}
    try:
        evidence = proof(key, node.revision)
        # 未到核验时点的证明不用于这次状态查询。
        verified = (proof_applies(evidence, node_id=key, revision=node.revision,
                                  content_sha=node.content_sha, source_id=meta['source_attribution']['source_id'],
                                  required_scope='full') and evidence['verified_at'] <= now)
    except (OSError, ValueError, TypeError, RecursionError):
        verified = False
    return {'status': 'verified' if verified else 'unverified',
            'locator': {'id': key, 'revision': node.revision, 'content_sha': node.content_sha}}
