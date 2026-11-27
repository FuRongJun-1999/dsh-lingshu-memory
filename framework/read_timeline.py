"""显式时轴上的授权时间线；先筛选，后排序和截断。"""
from framework.conditions import bitemporal_match, condition_match
from framework.contracts import extract_condition_space
from framework.migration import instant, interval
from framework.security import context_shape, integer


def read_timeline(*, axis, point, condition_query, limit, context, now, view, model):
    """使用同一受信快照；不返回正文、原区间、计数或隐边信息。"""
    if type(axis) is not str or axis not in ('observed', 'effective'):
        raise ValueError('AXIS_REQUIRED')
    if not integer(limit) or not 1 <= limit <= 100:
        raise ValueError('INVALID_LIMIT')
    instant(point)
    try:
        actor = context_shape(context)
    except (ValueError, TypeError, RecursionError):
        return {'error': 'AUTH_REQUIRED'}
    if not integer(now) or now >= actor['expires_at']:
        return {'error': 'AUTH_REQUIRED'}
    if view.policy_generation != actor['policy_generation']:
        return {'error': 'POLICY_CHANGED'}
    query = extract_condition_space(condition_query)
    rows = []
    for key, node in view.nodes.items():
        if not model.can_read(key, view.nodes, tenant=actor['tenant'], principal=actor['principal'], clearance=actor['clearance']):
            continue
        meta = view.metadata[key]
        if condition_match(meta['condition_space'],query) != 'MATCH':
            continue
        if bitemporal_match(meta['bitemporal'], {axis:point}) != 'MATCH':
            continue
        start, _ = interval(meta['bitemporal'][axis])
        # 左侧开放可以判定适用，但没有可排序的起点，不虚构时间。
        if start[0] != 'instant':
            continue
        rows.append((start[1],key,dict(id=key,revision=node.revision,content_sha=node.content_sha)))
    rows.sort(key=lambda row: row[1])
    rows.sort(key=lambda row: row[0], reverse=True)
    return dict(axis=axis, items=[row[2] for row in rows[:limit]])
