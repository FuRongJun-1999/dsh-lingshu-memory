"""源读取共同闸门；可信宿主提供授权和不可变字节，不接路径。"""
import hashlib
import re
from framework.security import context_shape, integer

MAX_BYTES = 1048576
IDENT = re.compile(r'[a-z][a-z0-9_.-]{0,127}')
HEX = re.compile(r'[0-9a-f]{64}')


def authorized_source(*, source_id, expected_sha, context, now, authorize, snapshot):
    """先授权，再校验 UTF-8 和整源版本；失败返回错误名而非文本。"""
    if type(source_id) is not str or IDENT.fullmatch(source_id) is None:
        raise ValueError('INVALID_SOURCE_ID')
    if type(expected_sha) is not str or HEX.fullmatch(expected_sha) is None:
        raise ValueError('INVALID_REFERENCE_DIGEST')
    try:
        actor = context_shape(context)
    except (ValueError, TypeError, RecursionError):
        return 'AUTH_REQUIRED', None
    if not integer(now) or now >= actor['expires_at']:
        return 'AUTH_REQUIRED', None
    if authorize(actor,source_id) is not True:
        return 'NOT_FOUND_OR_DENIED', None
    raw = snapshot(actor,source_id)
    if raw is None:
        return 'NOT_FOUND_OR_DENIED', None
    if type(raw) is not bytes or len(raw)>MAX_BYTES:
        return 'UNSUPPORTED_SOURCE', None
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        return 'SOURCE_CHANGED', None
    try:
        raw.decode('utf-8')
    except UnicodeDecodeError:
        return 'UNSUPPORTED_SOURCE', None
    return None, raw
