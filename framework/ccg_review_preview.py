"""六要素复核准入预演，不签章、不写节点。"""
import re
from framework.security import context_shape, integer
from framework.spec import digest

FIELDS=('功能名','生效条件','子功能','执行','验证方式','不适用条件')
ID=re.compile(r'[a-z0-9][a-z0-9_.:-]{0,127}')


def review_preview(*, node_id, expected_sha, context, now, allowed, snapshot, check_receipt):
    """check_receipt 是可信宿主的验证口；统一主体 ID，不接自报裁决。"""
    if (type(node_id) is not str or ID.fullmatch(node_id) is None or type(expected_sha) is not str
            or re.fullmatch(r'[0-9a-f]{64}',expected_sha) is None):
        raise ValueError('INVALID_CCG_SELECTOR')
    try:
        actor=context_shape(context)
    except (TypeError,ValueError,RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now>=actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if allowed(actor,node_id) is not True:
        return {'error':'CCG_DENIED'}
    candidate=snapshot(actor,node_id)
    if (type(candidate) is not dict or set(candidate)!={'node_id','compiler','policy_generation','fields'}
            or candidate['node_id']!=node_id or not integer(candidate['policy_generation'])
            or type(candidate['compiler']) is not str or ID.fullmatch(candidate['compiler']) is None):
        return {'error':'CCG_CANDIDATE_INVALID'}
    if candidate['policy_generation']!=actor['policy_generation']:
        return {'error':'POLICY_CHANGED'}
    fields=candidate['fields']
    if (type(fields) is not dict or set(fields)!=set(FIELDS) or any(type(v) is not str or not v.strip()
            or len(v)>4096 or any(0xd800<=ord(ch)<=0xdfff for ch in v) for v in fields.values())):
        return {'error':'CCG_FIELDS_INVALID'}
    if digest(candidate)!=expected_sha:
        return {'error':'CCG_CANDIDATE_CHANGED'}
    review=check_receipt(actor,node_id,expected_sha)
    if (type(review) is not dict or set(review)!={'node_id','candidate_sha','reviewer','policy_generation','verdict'}
            or review['node_id']!=node_id or review['candidate_sha']!=expected_sha
            or not integer(review['policy_generation']) or review['policy_generation']!=actor['policy_generation']
            or type(review['reviewer']) is not str or ID.fullmatch(review['reviewer']) is None):
        return {'error':'CCG_RECEIPT_UNVERIFIED'}
    if review['reviewer']==candidate['compiler']:
        return {'error':'CCG_SELF_REVIEW'}
    if review['verdict']!='ACCEPT':
        return {'error':'CCG_NOT_ACCEPTED'}
    return dict(status='review_matches',candidate_sha=expected_sha,applied=False)
