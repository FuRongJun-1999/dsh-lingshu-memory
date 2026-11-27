"""授权薄状态卡；维度指针不是权限、身份或信任证据。"""
import re
from framework.security import context_shape, integer

DIMS=('task','person','session','time','trust')


def read_self_card(*, subject, generation, context, now, allowed, snapshot):
    """可信端口须在同一权限快照为每个指针单独授权。"""
    if (type(subject) is not str or re.fullmatch(r'[a-zA-Z0-9_.:-]{1,128}',subject) is None
            or not integer(generation)):
        raise ValueError('INVALID_SELF_CARD_SELECTOR')
    try:
        actor=context_shape(context)
    except (ValueError,TypeError,RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now>=actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if allowed(actor,subject) is not True:
        return {'error':'NOT_FOUND_OR_DENIED'}
    row=snapshot(actor,subject)
    if row is None:
        return {'error':'NOT_FOUND_OR_DENIED'}
    if (type(row) is not dict or set(row)!={'subject','generation','policy_generation','dimensions'}
            or row['subject']!=subject or not integer(row['generation']) or not integer(row['policy_generation'])):
        return {'error':'SELF_CARD_INVALID'}
    if row['generation']!=generation or row['policy_generation']!=actor['policy_generation']:
        return {'error':'SELF_CARD_CHANGED'}
    dims=row['dimensions']
    if type(dims) is not dict or set(dims)!=set(DIMS):
        return {'error':'SELF_CARD_INVALID'}
    values={}
    for key in DIMS:
        ref=dims[key]
        if ref is not None and (type(ref) is not dict or set(ref)!={'id','revision','content_sha'}
                or type(ref['id']) is not str or re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}',ref['id']) is None
                or not integer(ref['revision']) or ref['revision']==0
                or type(ref['content_sha']) is not str or re.fullmatch(r'[0-9a-f]{64}',ref['content_sha']) is None):
            return {'error':'SELF_CARD_INVALID'}
        values[key]=None if ref is None else dict(ref)
    return dict(subject=subject,generation=generation,dimensions=values)
