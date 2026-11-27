"""冻结理论声明的只读核对，不改变启动状态。"""
import re
from framework.security import context_shape, integer
from framework.spec import digest

VERSION = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}')
SHA = re.compile(r'[0-9a-f]{64}')


def check_declaration(*, expected_sha, accepted, context, now, allowed, snapshot):
    """版本集合和摘要均是宿主信任锚，不取自声明自身。"""
    if (type(expected_sha) is not str or SHA.fullmatch(expected_sha) is None or type(accepted) is not frozenset
            or not 1<=len(accepted)<=32 or any(type(v) is not str or VERSION.fullmatch(v) is None for v in accepted)):
        raise ValueError('INVALID_THEORY_POLICY')
    try:
        actor=context_shape(context)
    except (ValueError,TypeError,RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now>=actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if allowed(actor) is not True:
        return {'error':'THEORY_DENIED'}
    frame=snapshot(actor)
    if frame is None:
        return {'status':'undeclared'}
    if (type(frame) is not dict or set(frame)!={'format','version','policy_generation'}
            or type(frame['format']) is not int or frame['format']!=1
            or not integer(frame['policy_generation']) or type(frame['version']) is not str
            or VERSION.fullmatch(frame['version']) is None):
        return {'error':'THEORY_SCHEMA_INVALID'}
    if frame['policy_generation']!=actor['policy_generation']:
        return {'error':'POLICY_CHANGED'}
    if digest(frame)!=expected_sha:
        return {'error':'THEORY_DECLARATION_CHANGED'}
    if frame['version'] not in accepted:
        return {'status':'version_not_accepted'}
    return dict(status='declaration_matches',version=frame['version'])
