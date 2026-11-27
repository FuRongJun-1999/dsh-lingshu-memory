"""授权当前修订的单轴时间证据检查；不返回原始时间元数据。"""
from framework.conditions import condition_match
from framework.contracts import extract_condition_space
from framework.migration import instant, interval
from framework.security import context_shape, integer


def diagnose_time(bounds, point):
    """先识别确定冲突，未知端点不能伪造通过；正常区间使用半开语义。"""
    try:
        left, right = interval(bounds)
    except ValueError as exc:
        return ('conflict', 'inverted_interval') if str(exc) == 'REVERSED_INTERVAL' else ('conflict', 'invalid_interval')
    if left[0] == right[0] == 'instant' and left[1] == right[1]:
        return 'conflict', 'empty_interval'
    if (left[0] == 'instant' and point < left[1]) or (right[0] == 'instant' and point >= right[1]):
        return 'conflict', 'outside_interval'
    if 'unknown' in (left[0],right[0]):
        return 'unknown', 'unknown_bound'
    return 'consistent', None


def check_time(*, node_id, axis, point, condition_query, context, now, view, model):
    """消费调用方已锁定的快照，不修复元数据，不生成验证凭据。"""
    if type(node_id) is not str or not node_id.strip() or len(node_id) > 128:
        raise ValueError('INVALID_NODE_ID')
    node_id.encode('utf-8')
    if type(axis) is not str or axis not in ('observed','effective'):
        raise ValueError('AXIS_REQUIRED')
    requested = instant(point)
    try:
        actor = context_shape(context)
    except (ValueError, TypeError, RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now >= actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if actor['policy_generation'] != view.policy_generation:
        return {'error':'POLICY_CHANGED'}
    if not model.can_read(node_id,view.nodes,tenant=actor['tenant'],principal=actor['principal'],clearance=actor['clearance']):
        return {'error':'NOT_FOUND_OR_DENIED'}
    meta = view.metadata[node_id]
    condition = condition_match(meta['condition_space'],extract_condition_space(condition_query))
    if condition == 'NO_MATCH':
        return {'status':'not_applicable'}
    if condition != 'MATCH':
        return {'error':'CONDITION_DEFERRED'}
    status, reason = diagnose_time(meta['bitemporal'].get(axis),requested)
    node = view.nodes[node_id]
    return dict(status=status,reason=reason,axis=axis,locator=dict(id=node_id,revision=node.revision,content_sha=node.content_sha))
