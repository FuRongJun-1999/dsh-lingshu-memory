"""按受信源 ID 回读 UTF-8 区间；没有宿主路径接口。"""
import hashlib
import re
from framework.security import context_shape, integer

MAX_BYTES = 1048576
IDENT = re.compile(r'[a-z][a-z0-9_.-]{0,127}')
HEX = re.compile(r'[0-9a-f]{64}')


def read_source_ref(ref, *, context, now, authorize, snapshot):
    """快照端口应只返回本次授权下已登记的不可变 bytes。"""
    if type(ref) is not dict or set(ref) != {'source_id','source_sha','start','end','region_sha'}:
        raise ValueError('INVALID_SOURCE_REFERENCE')
    key, start, end = ref['source_id'], ref['start'], ref['end']
    if type(key) is not str or IDENT.fullmatch(key) is None:
        raise ValueError('INVALID_SOURCE_ID')
    if not integer(start) or not integer(end) or not 1 <= start <= end or end-start >= 256:
        raise ValueError('INVALID_LINE_RANGE')
    if any(type(ref[k]) is not str or HEX.fullmatch(ref[k]) is None for k in ('source_sha','region_sha')):
        raise ValueError('INVALID_REFERENCE_DIGEST')
    try:
        actor = context_shape(context)
    except (ValueError, TypeError, RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now >= actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if authorize(actor,key) is not True:
        return {'error':'NOT_FOUND_OR_DENIED'}
    raw = snapshot(actor,key)
    if raw is None:
        return {'error':'NOT_FOUND_OR_DENIED'}
    if type(raw) is not bytes or len(raw)>MAX_BYTES:
        return {'error':'UNSUPPORTED_SOURCE'}
    if hashlib.sha256(raw).hexdigest() != ref['source_sha']:
        return {'error':'SOURCE_CHANGED'}
    try:
        raw.decode('utf-8')
    except UnicodeDecodeError:
        return {'error':'UNSUPPORTED_SOURCE'}
    # 只按 LF 分行，保留选中行原始的 LF/CRLF 和末行字节。
    parts = raw.split(b'\n',end)
    line_count = len(parts) - (parts[-1] == b'')
    if end > line_count:
        return {'error':'REGION_NOT_FOUND'}
    region = b'\n'.join(parts[start-1:end]) + (b'\n' if len(parts)>end else b'')
    if hashlib.sha256(region).hexdigest() != ref['region_sha']:
        return {'error':'REGION_CHANGED'}
    return {'locator':dict(ref),'text':region.decode('utf-8'),'trust':'untrusted_source'}
