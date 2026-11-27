"""固定证据的白箱回读探针，不调用问答模型。"""
import hashlib
import re
from framework.contracts import validate_v2_request
from framework.read_get import read_get
from framework.security import integer


def verify_existing(request, *, expected_revision, expected_sha, context, now, request_id,
                    snapshot, body, model, current_context, current_now):
    """预期来自独立受信夹具；只验证本次实际回读，不输出正文。"""
    req=validate_v2_request(request)
    if req['kind']!='Read.get' or req['include_provenance']:
        raise ValueError('PROBE_SELECTOR_REQUIRED')
    if (not integer(expected_revision) or expected_revision==0 or type(expected_sha) is not str
            or re.fullmatch(r'[0-9a-f]{64}',expected_sha) is None):
        raise ValueError('INVALID_PROBE_EXPECTATION')
    result=read_get(req,context=context,now=now,request_id=request_id,snapshot=snapshot,body=body,
                    model=model,current_context=current_context,current_now=current_now)
    if result['outcome']!='ok':
        return {'status':'unverified','reason':result['error_code']}
    if len(result['records'])!=1:
        return {'status':'unverified','reason':'PROBE_NO_EVIDENCE'}
    row=result['records'][0]
    expected=dict(id=req['node_id'],revision=expected_revision,content_sha=expected_sha)
    if row['locator']!=expected or hashlib.sha256(row['body'].encode('utf-8')).hexdigest()!=expected_sha:
        return {'status':'unverified','reason':'PROBE_MISMATCH'}
    return {'status':'verified_readback','locator':expected}
