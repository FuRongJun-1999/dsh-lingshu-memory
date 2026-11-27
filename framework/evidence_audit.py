"""授权单节点的只读证据审计；只组装当前核验态和可见来源。"""
from framework.contracts import validate_v2_request
from framework.read_edges import read_edges
from framework.read_status import read_status
from framework.security import context_shape, integer


def evidence_audit(request, *, context, now, view, model, can_audit, proof, limit):
    """所有读口须由同一受信快照和上下文提供；不读取正文。"""
    req = validate_v2_request(request)
    if req['kind'] != 'Read.get' or req['include_provenance']:
        raise ValueError('AUDIT_SELECTOR_REQUIRED')
    if not integer(limit) or not 1 <= limit <= 64:
        raise ValueError('INVALID_AUDIT_LIMIT')
    try:
        actor = context_shape(context)
    except (ValueError, TypeError, RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now >= actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if can_audit(actor,req['node_id']) is not True:
        return {'error':'NOT_FOUND_OR_DENIED'}
    common = dict(context=actor,now=now,view=view,model=model)
    sources = read_edges(req,**common)
    if 'locator' not in sources:
        return sources
    current = read_status(req,proof=proof,**common)
    if current.get('locator') != sources['locator'] or current.get('status') not in ('verified','unverified'):
        return {'error':'EVIDENCE_CHANGED'}
    return dict(locator=current['locator'], verification=current['status'], sources=sources['edges'][:limit])
