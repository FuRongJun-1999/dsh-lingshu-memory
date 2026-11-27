"""受信单会话事件窗口；不持久化、不触发状态抽取。"""
from framework.security import context_shape, integer

ROLES = frozenset(('user', 'assistant', 'tool-output', 'command'))
MAX_EVENTS = 256


def recent_window(*, session, roles, limit, expected_generation, context, now, allowed, snapshot):
    """快照端口在本次授权下提供单会话版本和按序事件。"""
    if type(session) is not str or not session.strip() or len(session)>128:
        raise ValueError('INVALID_SESSION')
    session.encode('utf-8')
    if (type(roles) is not frozenset or not roles or not roles <= ROLES or not integer(limit)
            or not 1<=limit<=MAX_EVENTS or not integer(expected_generation)):
        raise ValueError('INVALID_WINDOW')
    try:
        actor = context_shape(context)
    except (TypeError, ValueError, RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now>=actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if allowed(actor,session) is not True:
        return {'error':'NOT_FOUND_OR_DENIED'}
    frame = snapshot(actor,session)
    if frame is None:
        return {'error':'NOT_FOUND_OR_DENIED'}
    if (type(frame) is not dict or set(frame)!={'generation','events'} or not integer(frame['generation'])
            or type(frame['events']) is not tuple or len(frame['events'])>MAX_EVENTS):
        return {'error':'WINDOW_INVALID'}
    if frame['generation'] != expected_generation:
        return {'error':'WINDOW_CHANGED'}
    items, previous = [], 0
    for row in frame['events']:
        if (type(row) is not dict or set(row)!={'session','seq','role','text'} or row['session']!=session
                or not integer(row['seq']) or row['seq']<=previous or type(row['role']) is not str
                or row['role'] not in ROLES or type(row['text']) is not str or len(row['text'])>4096):
            return {'error':'WINDOW_INVALID'}
        try:
            row['text'].encode('utf-8')
        except UnicodeEncodeError:
            return {'error':'WINDOW_INVALID'}
        previous=row['seq']
        if row['role'] in roles:
            items.append(dict(seq=previous,role=row['role'],text=row['text'],trust='untrusted_event'))
    return dict(generation=expected_generation,events=list(reversed(items[-limit:])))
