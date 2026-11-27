"""只读预演显式下游失效，不写验证态。"""
from collections import deque
from framework.read_edges import read_edges
from framework.security import integer


def preview_propagation(request, *, context, now, view, model, states, downstream, budget):
    """受信状态和依赖边按同快照精确定位符索引，宿主负责验证其来源。"""
    if not integer(budget) or not 1<=budget<=512:
        raise ValueError('INVALID_PROPAGATION_BUDGET')
    def get(key):
        row=read_edges(dict(request,node_id=key),context=context,now=now,view=view,model=model)
        loc=row.get('locator')
        return row,None if loc is None else (loc['id'],loc['revision'],loc['content_sha'])

    root,first=get(request['node_id'])
    if first is None:
        return root
    if states.get(first) not in ('expired','rechecking'):
        return {'error':'PROPAGATION_ROOT_UNCONFIRMED'}
    work=deque([first]); seen={first}; planned=[]; checked=0
    while work:
        source=work.popleft()
        for ref in downstream.get(source,()):
            checked+=1
            if checked>budget:
                return {'error':'PROPAGATION_BUDGET'}
            if ref in seen:
                continue
            seen.add(ref)
            row,current=get(ref[0])
            if current!=ref:
                continue
            state=states.get(ref)
            if state not in ('verified','doubted','expired','rechecking'):
                return {'error':'PROPAGATION_STATE_UNKNOWN'}
            if state=='verified':
                planned.append(row['locator'])
            work.append(ref)
    return dict(root=root['locator'],planned=sorted(planned,key=lambda x:x['id']),applied=False)
