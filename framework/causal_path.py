"""显式条件依赖的授权路径；不从来源边或语义相似推断因果。"""
from collections import deque
from framework.contracts import validate_v2_request
from framework.read_edges import read_edges
from framework.security import integer


def conditional_path(request, *, target, depth, context, now, view, model, bindings):
    """bindings 由受信宿主和 view 同一快照提供：源定位组三元组到目标定位组三元组。"""
    req=validate_v2_request(request)
    if req['kind']!='Read.get' or req['include_provenance'] or type(target) is not str or not target:
        raise ValueError('PATH_SELECTOR_REQUIRED')
    if not integer(depth) or not 1<=depth<=8:
        raise ValueError('INVALID_PATH_DEPTH')

    def inspect(key):
        result=read_edges(dict(req,node_id=key),context=context,now=now,view=view,model=model)
        loc=result.get('locator')
        return result, None if loc is None else (loc['id'],loc['revision'],loc['content_sha'])

    root, first=inspect(req['node_id'])
    if first is None:
        return root
    _, end=inspect(target)
    if end is None or first==end:
        return {'status':'no_visible_path'}
    pending=deque([(first,)]); seen={first}; examined=0
    while pending:
        path=pending.popleft()
        if len(path)>depth:
            continue
        for candidate in bindings.get(path[-1],()):
            examined+=1
            if examined>512:
                return {'error':'PATH_BUDGET'}
            if candidate in seen:
                continue
            _, current=inspect(candidate[0])
            if current is None or current!=candidate:
                continue
            route=path+(current,)
            if current==end:
                return {'status':'visible_path','path':[dict(id=k,revision=r,content_sha=s) for k,r,s in route]}
            seen.add(current)
            pending.append(route)
    return {'status':'no_visible_path'}
