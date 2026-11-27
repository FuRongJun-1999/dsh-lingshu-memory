"""单主体画像引用，不生成身份、凭据或授权。"""
import re
from framework.security import context_shape, integer
from framework.spec import digest


def identity_profile(*, subject, expected_sha, context, now, allowed, snapshot):
    """宿主在同一权限快照中逐条授权引用，独立锚定摘要。"""
    if (type(subject) is not str or re.fullmatch(r'[a-zA-Z0-9_.:-]{1,128}',subject) is None
            or type(expected_sha) is not str or re.fullmatch(r'[0-9a-f]{64}',expected_sha) is None):
        raise ValueError('INVALID_PROFILE_SELECTOR')
    try:
        actor=context_shape(context)
    except (ValueError,TypeError,RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now>=actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if allowed(actor,subject) is not True:
        return {'error':'NOT_FOUND_OR_DENIED'}
    frame=snapshot(actor,subject)
    if frame is None:
        return {'error':'NOT_FOUND_OR_DENIED'}
    if (type(frame) is not dict or set(frame)!={'subject','refs'} or frame['subject']!=subject
            or type(frame['refs']) is not list or len(frame['refs'])>32):
        return {'error':'PROFILE_INVALID'}
    refs=[];seen=set()
    for row in frame['refs']:
        if (type(row) is not dict or set(row)!={'kind','id','revision','content_sha'}
                or type(row['kind']) is not str or row['kind'] not in ('anchor','trait')
                or type(row['id']) is not str or re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}',row['id']) is None
                or row['id'] in seen or not integer(row['revision']) or row['revision']==0
                or type(row['content_sha']) is not str or re.fullmatch(r'[0-9a-f]{64}',row['content_sha']) is None):
            return {'error':'PROFILE_INVALID'}
        seen.add(row['id']);refs.append(dict(row))
    if digest(dict(subject=subject,refs=refs))!=expected_sha:
        return {'error':'PROFILE_CHANGED'}
    return dict(subject=subject,refs=refs)
