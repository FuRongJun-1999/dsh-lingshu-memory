"""情境记忆提升候选预演；只给计划，不移动节点。"""
from framework.read_edges import read_edges
from framework.security import integer


def preview_promotion(request, *, context, now, view, model, can_plan, evidence, min_hits, min_importance_bp):
    """宿主提供同一临界区的权限及逐修订六要素判据证据。"""
    if not integer(min_hits) or min_hits==0 or not integer(min_importance_bp) or not 1<=min_importance_bp<=10000:
        raise ValueError('INVALID_PROMOTION_THRESHOLDS')
    selected=read_edges(request,context=context,now=now,view=view,model=model)
    locator=selected.get('locator')
    if locator is None:
        return selected
    if can_plan(context) is not True:
        return {'error':'PROMOTION_DENIED'}
    key=(locator['id'],locator['revision'],locator['content_sha'])
    row=evidence(key)
    if (type(row) is not dict or set(row)!={'key','layer','complete','locked','hits','importance_bp'}
            or row['key']!=key or type(row['layer']) is not str
            or type(row['complete']) is not bool or type(row['locked']) is not bool
            or not integer(row['hits']) or not integer(row['importance_bp']) or row['importance_bp']>10000):
        return {'error':'PROMOTION_EVIDENCE_UNKNOWN'}
    if row['layer']!='contextual' or row['locked'] or not row['complete']:
        return {'status':'not_eligible'}
    if row['hits']<min_hits and row['importance_bp']<min_importance_bp:
        return {'status':'not_eligible'}
    return dict(status='candidate',locator=locator,target_layer='knowledge',applied=False)
