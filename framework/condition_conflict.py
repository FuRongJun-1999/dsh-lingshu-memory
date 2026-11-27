"""对已授权的显式正负条件做精确交叉对照，不写台账。"""
import re
from framework.read_edges import read_edges

TERM = re.compile(r'[a-z][a-z0-9_.-]{0,63}')


def _terms(value):
    return (type(value) is frozenset and len(value)<=64
            and all(type(x) is str and TERM.fullmatch(x) is not None for x in value))


def check_conditions(request, *, positive, negative, context, now, view, model, bindings):
    """宿主提供同快照中当前定位符索引的受信声明；不读正文。"""
    if not _terms(positive) or not _terms(negative) or not positive|negative or positive&negative:
        raise ValueError('INVALID_DECLARED_CONDITIONS')
    result = read_edges(request,context=context,now=now,view=view,model=model)
    anchor = result.get('locator')
    if anchor is None:
        return result
    rows = bindings.get((anchor['id'],anchor['revision'],anchor['content_sha']))
    if type(rows) is not tuple or len(rows)>128:
        return {'error':'CONDITION_SCOPE_UNKNOWN'}
    conflicts=[]; compared=set()
    for key, revision, sha, declared, excluded in rows:
        candidate=read_edges(dict(request,node_id=key),context=context,now=now,view=view,model=model).get('locator')
        if candidate is None or (candidate['revision'],candidate['content_sha'])!=(revision,sha):
            continue
        if key==anchor['id'] or key in compared or not _terms(declared) or not _terms(excluded) or declared&excluded:
            return {'error':'CONDITION_SCOPE_UNKNOWN'}
        compared.add(key)
        overlap=(positive&excluded)|(negative&declared)
        if overlap:
            conflicts.append(dict(locator=candidate,conditions=sorted(overlap)))
    conflicts.sort(key=lambda row:row['locator']['id'])
    return dict(status='EXACT_CONFLICT' if conflicts else 'NO_EXACT_CONFLICT',conflicts=conflicts)
