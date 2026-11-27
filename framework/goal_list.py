"""授权且绑定当前修订的显式目标候选排序，不写目标。"""
from framework.contracts import validate_v2_request
from framework.read_edges import read_edges
from framework.security import context_shape, integer

STATES = frozenset(('active','done','dropped'))


def list_goals(request, *, candidates, status, limit, context, now, view, model, labels):
    """候选及标签来自本次可信快照；标签键是精确定位组三元组。"""
    req = validate_v2_request(request)
    if req['kind'] != 'Read.get' or req['include_provenance']:
        raise ValueError('GOAL_SELECTOR_REQUIRED')
    if type(status) is not str or status not in STATES or not integer(limit) or not 1<=limit<=32:
        raise ValueError('INVALID_GOAL_WINDOW')
    if (type(candidates) is not tuple or len(candidates)>128
            or any(type(k) is not str or not k for k in candidates)):
        raise ValueError('INVALID_GOAL_CANDIDATES')
    try:
        actor = context_shape(context)
    except (TypeError, ValueError, RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now>=actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if view.policy_generation!=actor['policy_generation']:
        return {'error':'POLICY_CHANGED'}
    out=[]
    for key in dict.fromkeys(candidates):
        row=read_edges(dict(req,node_id=key),context=actor,now=now,view=view,model=model)
        locator=row.get('locator')
        if locator is None:
            continue
        mark=labels.get((key,locator['revision'],locator['content_sha']))
        if mark is None:
            continue
        if (type(mark) is not tuple or len(mark)!=2 or type(mark[0]) is not str or mark[0] not in STATES
                or not integer(mark[1]) or mark[1]>100):
            return {'error':'GOAL_LABEL_INVALID'}
        if mark[0]==status:
            out.append(dict(locator=locator,status=status,priority=mark[1]))
    out.sort(key=lambda x:(-x['priority'],x['locator']['id']))
    return {'goals':out[:limit]}
