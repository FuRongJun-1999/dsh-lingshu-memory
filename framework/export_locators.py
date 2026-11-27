"""内存中的显式节点导出清单；不读取正文、写文件或发送。"""
import re
from framework.contracts import validate_v2_request
from framework.read_edges import read_edges
from framework.security import context_shape, integer


def export_locators(request, *, expected, generation, context, now, view, model, can_export):
    """可信宿主提供认证、导出授权及同一临界区的不可变快照。"""
    req=validate_v2_request(request)
    if req['kind']!='Read.get' or req['include_provenance']:
        raise ValueError('EXPORT_SELECTOR_REQUIRED')
    if type(expected) is not tuple or not 1<=len(expected)<=64 or not integer(generation):
        raise ValueError('INVALID_EXPORT_SCOPE')
    keys=set()
    for item in expected:
        if (type(item) is not tuple or len(item)!=3 or type(item[0]) is not str or not 1<=len(item[0])<=128
                or not integer(item[1]) or item[1]==0 or type(item[2]) is not str
                or re.fullmatch(r'[0-9a-f]{64}',item[2]) is None or item[0] in keys):
            raise ValueError('INVALID_EXPORT_SCOPE')
        keys.add(item[0])
    try:
        actor=context_shape(context)
    except (ValueError,TypeError,RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now>=actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if can_export(actor) is not True:
        return {'error':'EXPORT_DENIED'}
    if view.policy_generation!=actor['policy_generation']:
        return {'error':'POLICY_CHANGED'}
    if view.content_generation!=generation:
        return {'error':'EXPORT_SNAPSHOT_CHANGED'}
    out=[]
    for key, revision, sha in sorted(expected):
        row=read_edges(dict(req,node_id=key),context=actor,now=now,view=view,model=model).get('locator')
        if row!=dict(id=key,revision=revision,content_sha=sha):
            return {'error':'EXPORT_SCOPE_UNAVAILABLE'}
        out.append(row)
    return dict(format='locator_manifest_v1',generation=generation,nodes=out)
