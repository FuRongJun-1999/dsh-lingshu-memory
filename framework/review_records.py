"""已授权提案的摘要绑定裁决元数据；不改变裁决。"""
import re
from framework.security import context_shape, integer
from framework.spec import digest

DECISIONS = frozenset(('accept','reject','edit','merge','noop'))


def review_records(*, proposal, expected_sha, context, now, allowed, snapshot, limit):
    """摘要由可信宿主独立提供；不是签名，不校验旧账格式。"""
    if (type(proposal) is not str or re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}',proposal) is None
            or type(expected_sha) is not str or re.fullmatch(r'[0-9a-f]{64}',expected_sha) is None
            or not integer(limit) or not 1<=limit<=32):
        raise ValueError('INVALID_REVIEW_SELECTOR')
    try:
        actor=context_shape(context)
    except (ValueError,TypeError,RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now>=actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if allowed(actor,proposal) is not True:
        return {'error':'NOT_FOUND_OR_DENIED'}
    frame=snapshot(actor,proposal)
    if frame is None:
        return {'error':'NOT_FOUND_OR_DENIED'}
    if (type(frame) is not dict or set(frame)!={'proposal','records'} or frame['proposal']!=proposal
            or type(frame['records']) is not list or len(frame['records'])>128):
        return {'error':'REVIEW_RECORD_INVALID'}
    records=[]
    previous=0
    for row in frame['records']:
        if (type(row) is not dict or set(row)!={'seq','decision','revision'}
                or not integer(row['seq']) or row['seq']<=previous
                or type(row['decision']) is not str or row['decision'] not in DECISIONS
                or not integer(row['revision']) or row['revision']==0):
            return {'error':'REVIEW_RECORD_INVALID'}
        previous=row['seq'];records.append(dict(row))
    if digest(dict(proposal=proposal,records=records))!=expected_sha:
        return {'error':'REVIEW_RECORD_CHANGED'}
    return dict(proposal=proposal,records=list(reversed(records[-limit:])))
