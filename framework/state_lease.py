"""单槽状态租约。取用已校验的投影；不授权、不查盘、不选择 TTL。"""
from framework.security import integer


def lease_view(projection, *, now, ttl_seconds):
    """租约到期仅标记 weak，不清除现值；不把未知或冲突改写为空。"""
    if not integer(now) or not integer(ttl_seconds) or ttl_seconds == 0:
        raise ValueError('INVALID_LEASE_TIME')
    if type(projection) is not dict:
        raise ValueError('INVALID_STATE_PROJECTION')
    if 'error' in projection:
        return {'error': projection['error']}
    status = projection.get('status')
    if status == 'unknown':
        return {'status': 'unknown', 'reason': projection['reason']}
    if status == 'empty':
        return {'status': 'empty'}
    if status not in ('active','retired') or not integer(projection.get('seq')) or not projection['seq']:
        raise ValueError('INVALID_STATE_PROJECTION')
    recorded = projection.get('recorded_at')
    if not integer(recorded) or recorded > now:
        return {'status':'unknown','reason':'INVALID_RECORDED_TIME'}
    base = dict(seq=projection['seq'], recorded_at=recorded)
    if status == 'retired':
        return dict(base,status='retired')
    value = projection.get('value')
    if type(value) is not str or not value.strip():
        raise ValueError('INVALID_STATE_PROJECTION')
    age = now - recorded
    return dict(base,status='weak' if age >= ttl_seconds else 'stable',value=value,
                age_seconds=age,ttl_seconds=ttl_seconds)
