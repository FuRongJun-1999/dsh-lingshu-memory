"""已固定来源的 JSONL 事件摄取预演，不推进水位。"""
from framework.security import integer
from framework.source_snapshot import authorized_source
from framework.spec import parse


def preview_ingest(*, source_id, expected_sha, watermark, limit, context, now, allowed, snapshot):
    """水位由受信宿主按同一来源提供；结果不构成写入授权。"""
    if not integer(watermark) or not integer(limit) or not 1 <= limit <= 128:
        raise ValueError('INVALID_INGEST_WINDOW')
    error, raw = authorized_source(source_id=source_id,expected_sha=expected_sha,context=context,
                                   now=now,authorize=allowed,snapshot=snapshot)
    if error is not None:
        return {'error':error}
    rows=raw.split(b'\n')
    if rows[-1]==b'':
        rows.pop()
    if len(rows)>256:
        return {'error':'INGEST_SCAN_BUDGET'}
    previous=0; count=0
    for line in rows:
        if len(line)>8192:
            return {'error':'INGEST_EVENT_INVALID'}
        try:
            item=parse(line.decode('utf-8'))
        except (ValueError,TypeError,RecursionError):
            return {'error':'INGEST_EVENT_INVALID'}
        if (type(item) is not dict or set(item)!={'source','seq','text'} or item['source']!=source_id
                or not integer(item['seq']) or item['seq']<=previous or type(item['text']) is not str):
            return {'error':'INGEST_EVENT_INVALID'}
        try:
            item['text'].encode('utf-8')
        except UnicodeEncodeError:
            return {'error':'INGEST_EVENT_INVALID'}
        previous=item['seq']
        if previous>watermark:
            count+=1
    if count>limit:
        return {'error':'INGEST_EVENT_BUDGET'}
    return dict(source=source_id,watermark=watermark,pending=count,applied=False)
