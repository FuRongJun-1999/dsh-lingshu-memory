"""授权单节点的来源出边投影；不读取正文、不报告被过滤边。"""
from framework.conditions import bitemporal_match, condition_match
from framework.contracts import extract_condition_space, validate_v2_request
from framework.security import context_shape, integer


def read_edges(request, *, context, now, view, model):
    """调用方提供同一临界区内的受信快照、上下文与时钟。"""
    req = validate_v2_request(request)
    if req['kind'] != 'Read.get' or req['include_provenance']:
        raise ValueError('EDGE_SELECTOR_REQUIRED')
    try:
        actor = context_shape(context)
    except (ValueError, TypeError, RecursionError):
        return {'error': 'AUTH_REQUIRED'}
    if not integer(now) or now >= actor['expires_at']:
        return {'error': 'AUTH_REQUIRED'}
    if view.policy_generation != actor['policy_generation']:
        return {'error': 'POLICY_CHANGED'}

    def allowed(key):
        return model.can_read(key, view.nodes, tenant=actor['tenant'], principal=actor['principal'],
                              clearance=actor['clearance'])

    query = extract_condition_space(req['condition_query'])
    point = {req['time_axis']: req['time_point']}

    def applicable(key):
        meta = view.metadata[key]
        parts = condition_match(meta['condition_space'], query), bitemporal_match(meta['bitemporal'], point)
        return 'NO_MATCH' if 'NO_MATCH' in parts else 'DEFER' if 'DEFER' in parts else 'MATCH'

    root = req['node_id']
    if not allowed(root):
        return {'error': 'NOT_FOUND_OR_DENIED'}
    status = applicable(root)
    if status == 'NO_MATCH':
        return {'status': 'not_applicable'}
    if status == 'DEFER':
        return {'error': 'CONDITION_DEFERRED'}
    node = view.nodes[root]
    edges = []
    # 只对授权、当前修订匹配且适用的端点投影。其他情况不产生计数。
    for edge in node.edges:
        if not allowed(edge.target) or edge.relation == 'unknown':
            continue
        target = view.nodes[edge.target]
        if (edge.revision, edge.content_sha) != (target.revision, target.content_sha) or applicable(edge.target) != 'MATCH':
            continue
        edges.append(dict(relation=edge.relation, target=dict(id=edge.target, revision=target.revision,
                                                            content_sha=target.content_sha)))
    return dict(locator=dict(id=root, revision=node.revision, content_sha=node.content_sha), edges=edges)
