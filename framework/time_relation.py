"""授权双节点的时间关系；只比较明确指定的单轴，不返回原区间。"""
from framework.conditions import condition_match
from framework.contracts import extract_condition_space
from framework.migration import interval
from framework.security import context_shape, integer


def classify(left, right):
    a, b = interval(left)
    c, d = interval(right)
    if any(x[0] == 'unknown' for x in (a, b, c, d)):
        return 'unknown'
    low, high = float('-inf'), float('inf')
    # 有限端点统一转换为 UTC 时间戳；开放端点不制造具体时刻。
    x, y, z, w = [(bound[1].timestamp() if bound[0] == 'instant' else fallback)
                  for bound, fallback in ((a,low),(b,high),(c,low),(d,high))]
    if x == y or z == w:
        return 'empty'
    if (x, y) == (z, w):
        return 'equals'
    if y <= z:
        return 'before'
    if x >= w:
        return 'after'
    if x <= z and y >= w:
        return 'contains'
    if x >= z and y <= w:
        return 'during'
    return 'overlaps'


def relate_time(*, a, b, axis, condition_query, context, now, view, model):
    """在受信快照内先校验双端授权，再读取条件及时间元数据。"""
    for name in (a,b):
        if type(name) is not str or not name.strip() or len(name) > 128:
            raise ValueError('INVALID_NODE_ID')
        name.encode('utf-8')
    if axis not in ('observed','effective'):
        raise ValueError('AXIS_REQUIRED')
    try:
        actor = context_shape(context)
    except (ValueError, TypeError, RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now >= actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if view.policy_generation != actor['policy_generation']:
        return {'error':'POLICY_CHANGED'}
    if not all(model.can_read(key, view.nodes, tenant=actor['tenant'], principal=actor['principal'],
                              clearance=actor['clearance']) for key in (a,b)):
        return {'error':'NOT_FOUND_OR_DENIED'}
    query = extract_condition_space(condition_query)
    ma, mb = view.metadata[a], view.metadata[b]
    verdicts = [condition_match(x['condition_space'],query) for x in (ma,mb)]
    if 'NO_MATCH' in verdicts:
        return {'status':'not_applicable'}
    if 'DEFER' in verdicts:
        return {'error':'CONDITION_DEFERRED'}

    def locate(key):
        row = view.nodes[key]
        return dict(id=key, revision=row.revision, content_sha=row.content_sha)

    return dict(axis=axis, a=locate(a), b=locate(b), relation=classify(ma['bitemporal'][axis], mb['bitemporal'][axis]))
