"""合成会话续接：同代际的要点引用和近期窗口，不写会话。"""
import re
from framework.security import integer
from framework.recent_window import recent_window


def resume_session(*, session, roles, recent_limit, expected_generation, byte_budget,
                   context, now, allowed, snapshot):
    """宿主已筛选要点的逐条权限；此处再核对归属、版本与预算。"""
    if not integer(byte_budget) or byte_budget>65536:
        raise ValueError('INVALID_SESSION_BUDGET')
    if byte_budget==0:
        return {'error':'SESSION_BUDGET'}
    notes = None

    def recent_frame(actor, key):
        nonlocal notes
        frame = snapshot(actor,key)
        if frame is None:
            return None
        if type(frame) is not dict or set(frame)!={'generation','events','notes'}:
            return {}
        notes = frame['notes']
        return {k:frame[k] for k in ('generation','events')}

    events = recent_window(session=session,roles=roles,limit=recent_limit,expected_generation=expected_generation,
                           context=context,now=now,allowed=allowed,snapshot=recent_frame)
    if 'error' in events:
        return events
    if type(notes) is not tuple or len(notes)>32:
        return {'error':'SESSION_NOTES_INVALID'}
    output=[]; seen=set()
    remaining=byte_budget-sum(len(e['text'].encode('utf-8')) for e in events['events'])
    for note in notes:
        if (type(note) is not dict or set(note)!={'session','id','revision','content_sha'}
                or type(note['session']) is not str or note['session']!=session
                or type(note['id']) is not str or re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}',note['id']) is None
                or not integer(note['revision']) or note['revision']==0
                or type(note['content_sha']) is not str or re.fullmatch(r'[0-9a-f]{64}',note['content_sha']) is None
                or note['id'] in seen):
            return {'error':'SESSION_NOTES_INVALID'}
        seen.add(note['id'])
        remaining-=len(note['id'])+64+len(str(note['revision']))
        output.append({k:note[k] for k in ('id','revision','content_sha')})
    if remaining<0:
        return {'error':'SESSION_BUDGET'}
    return dict(events,notes=output)
