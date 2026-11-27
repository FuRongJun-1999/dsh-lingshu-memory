"""静态构造 Python 顶层声明引用；不导入、执行或访问路径。"""
import ast
import hashlib
from framework.security import context_shape, integer
from framework.source_ref import HEX, IDENT, MAX_BYTES


def index_python(*, source_id, expected_sha, context, now, authorize, snapshot):
    """授权及版本确认后才解析；行号按 LF，保留 CRLF 原始字节。"""
    if type(source_id) is not str or IDENT.fullmatch(source_id) is None:
        raise ValueError('INVALID_SOURCE_ID')
    if type(expected_sha) is not str or HEX.fullmatch(expected_sha) is None:
        raise ValueError('INVALID_REFERENCE_DIGEST')
    try:
        actor = context_shape(context)
    except (ValueError, TypeError, RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now >= actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if authorize(actor,source_id) is not True:
        return {'error':'NOT_FOUND_OR_DENIED'}
    raw = snapshot(actor,source_id)
    if raw is None:
        return {'error':'NOT_FOUND_OR_DENIED'}
    if type(raw) is not bytes or len(raw)>MAX_BYTES:
        return {'error':'UNSUPPORTED_SOURCE'}
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        return {'error':'SOURCE_CHANGED'}
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        return {'error':'UNSUPPORTED_SOURCE'}
    if b'\r' in raw.replace(b'\r\n',b''):
        return {'error':'UNSUPPORTED_NEWLINES'}
    try:
        tree = ast.parse(text,filename='<registered-source>',feature_version=(3,11))
    except (SyntaxError, ValueError, RecursionError):
        return {'error':'INVALID_PYTHON'}
    parts = raw.split(b'\n')
    lines = [line+b'\n' for line in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
    items = []
    kinds = {ast.FunctionDef:'function',ast.AsyncFunctionDef:'async_function',ast.ClassDef:'class'}
    for node in tree.body:
        kind = kinds.get(type(node))
        if kind is None:
            continue
        start, end = node.lineno, node.end_lineno
        if len(items)>=64 or end-start>=256:
            return {'error':'DECLARATION_BUDGET'}
        # 声明从 def/class 行起；前置装饰器不属于该引用。
        region = b''.join(lines[start-1:end])
        items.append(dict(name=node.name,kind=kind,locator=dict(source_id=source_id,source_sha=expected_sha,
                          start=start,end=end,region_sha=hashlib.sha256(region).hexdigest())))
    return dict(declarations=items)
