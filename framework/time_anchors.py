"""授权时间窗锚点：只投影与有限窗口相交的当前修订。"""
from framework.conditions import condition_match
from framework.contracts import extract_condition_space
from framework.migration import instant, interval
from framework.security import context_shape, integer


def intersects(bounds, start, end):
    left, right = interval(bounds)
    if left[0] == 'unknown' or right[0] == 'unknown':
        return False
    if left[0] == right[0] == 'instant' and left[1] == right[1]:
        return False
    # 半开区间：等于查询端点时只接触，不相交；明确无界不等于未知。
    return (left[0] == 'unbounded' or left[1] < end) and (right[0] == 'unbounded' or start < right[1])


def time_anchors(*, axis, window_start, window_end, condition_query, limit, context, now, view, model):
    """调用者提供已校验快照、可信主体及时钟；不保留快照或授权。"""
    if type(axis) is not str or axis not in ('observed','effective'):
        raise ValueError('AXIS_REQUIRED')
    if not integer(limit) or not 1 <= limit <= 100:
        raise ValueError('INVALID_LIMIT')
    start, end = instant(window_start), instant(window_end)
    if start >= end:
        raise ValueError('INVALID_WINDOW')
    try:
        actor = context_shape(context)
    except (ValueError, TypeError, RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now >= actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if view.policy_generation != actor['policy_generation']:
        return {'error':'POLICY_CHANGED'}
    query = extract_condition_space(condition_query)
    items = []
    for key in sorted(view.nodes):
        if not model.can_read(key, view.nodes, tenant=actor['tenant'], principal=actor['principal'], clearance=actor['clearance']):
            continue
        meta = view.metadata[key]
        if condition_match(meta['condition_space'],query) != 'MATCH' or not intersects(meta['bitemporal'][axis],start,end):
            continue
        node = view.nodes[key]
        items.append(dict(id=key,revision=node.revision,content_sha=node.content_sha))
        if len(items) == limit:
            break
    return dict(axis=axis, items=items)
