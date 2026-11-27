"""授权的心跳时效投影，不启动循环或执行自愈。"""
import re
from framework.security import context_shape, integer


def heartbeat_status(*, service, generation, ttl, context, now, allowed, snapshot):
    """代际与时钟由可信宿主固定，读口返回已授权的当前记录。"""
    if (type(service) is not str or re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}',service) is None
            or not integer(generation) or not integer(ttl) or not 1<=ttl<=86400):
        raise ValueError('INVALID_HEARTBEAT_SELECTOR')
    try:
        actor=context_shape(context)
    except (ValueError,TypeError,RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now>=actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if allowed(actor,service) is not True:
        return {'error':'HEARTBEAT_DENIED'}
    row=snapshot(actor,service)
    if row is None:
        return {'status':'unknown'}
    if (type(row) is not dict or set(row)!={'service','generation','policy_generation','observed_at','busy'}
            or row['service']!=service or type(row['busy']) is not bool
            or any(not integer(row[k]) for k in ('generation','policy_generation','observed_at'))):
        return {'error':'HEARTBEAT_INVALID'}
    if (row['generation'],row['policy_generation'])!=(generation,actor['policy_generation']):
        return {'error':'HEARTBEAT_CHANGED'}
    age=now-row['observed_at']
    if age<0:
        return {'error':'HEARTBEAT_FUTURE'}
    if age>=ttl:
        return {'status':'stale'}
    return dict(status='fresh',age=age,reported_busy=row['busy'])
