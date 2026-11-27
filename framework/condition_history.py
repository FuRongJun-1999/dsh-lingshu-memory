"""当前修订的授权条件补充记录，只读。"""
from framework.read_edges import read_edges
from framework.security import integer


def condition_history(request, *, context, now, view, model, history, limit):
    """宿主在同一锁下提供已单独授权、严格按修订升序的记录。"""
    if not integer(limit) or not 1<=limit<=32:
        raise ValueError('INVALID_HISTORY_LIMIT')
    selected=read_edges(request,context=context,now=now,view=view,model=model)
    locator=selected.get('locator')
    if locator is None:
        return selected
    key=(locator['id'],locator['revision'],locator['content_sha'])
    frame=history(key)
    if type(frame) is not dict or set(frame)!={'key','changes'} or frame['key']!=key:
        return {'error':'HISTORY_UNKNOWN'}
    rows=frame['changes']
    if type(rows) is not tuple or len(rows)>128:
        return {'error':'HISTORY_UNKNOWN'}
    previous=0; visible=[]
    for change in rows:
        if (type(change) is not dict or set(change)!={'revision','rule','missing'}
                or not integer(change['revision']) or not previous<change['revision']<=locator['revision']
                or any(type(change[k]) is not str or not change[k].strip() or len(change[k])>512 for k in ('rule','missing'))):
            return {'error':'HISTORY_UNKNOWN'}
        try:
            for k in ('rule','missing'):
                change[k].encode('utf-8')
        except UnicodeEncodeError:
            return {'error':'HISTORY_UNKNOWN'}
        previous=change['revision']; visible.append(dict(change,trust='untrusted_history'))
    if visible and previous!=locator['revision']:
        return {'error':'HISTORY_UNKNOWN'}
    return dict(locator=locator,changes=list(reversed(visible[-limit:])))
