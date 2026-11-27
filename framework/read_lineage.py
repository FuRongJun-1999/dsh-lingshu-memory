"""只读派生谱系，不从普通来源边推导。"""
from framework.read_edges import read_edges
from framework.security import integer

RELATIONS = frozenset(('split_from','extracted_from','merged_from','refined_from','source'))


def read_lineage(request, *, relation, limit, context, now, view, model, bindings):
    """可信宿主在同一快照提供按子定位符索引的显式父关系。"""
    if type(relation) is not str or relation not in RELATIONS or not integer(limit) or not 1<=limit<=32:
        raise ValueError('INVALID_LINEAGE_FILTER')
    child = read_edges(request,context=context,now=now,view=view,model=model)
    locator = child.get('locator')
    if locator is None:
        return child
    records = bindings.get((locator['id'],locator['revision'],locator['content_sha']),())
    if type(records) is not tuple or len(records)>128:
        return {'error':'LINEAGE_BUDGET'}
    visible={}
    for kind, key, revision, sha in records:
        if kind!=relation:
            continue
        parent = read_edges(dict(request,node_id=key),context=context,now=now,view=view,model=model).get('locator')
        if parent is None or (parent['revision'],parent['content_sha'])!=(revision,sha):
            continue
        if parent['id']!=locator['id']:
            visible[key]=parent
    return dict(child=locator,relations=[dict(relation=relation,parent=visible[k]) for k in sorted(visible)[:limit]])
