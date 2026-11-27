"""已授权 Markdown 快照到精确章节引用；不触盘或写入索引。"""
import hashlib
import re
from framework.source_snapshot import authorized_source

FENCE = re.compile(rb' {0,3}(\x60{3,}|~{3,})([^\r\n]*)')
HEADING = re.compile(rb' {0,3}(#{1,6})(?:[ \t]+[^\r\n]*)?')
MAX_SECTIONS = 64


def index_document(*, source_id, expected_sha, context, now, authorize, snapshot):
    """仅接受登记源和固定版本；超限或格式不明不返回部分引用。"""
    error, raw = authorized_source(source_id=source_id,expected_sha=expected_sha,context=context,
                                   now=now,authorize=authorize,snapshot=snapshot)
    if error is not None:
        return {'error':error}
    pieces=raw.split(b'\n')
    lines=[p+b'\n' for p in pieces[:-1]]+([pieces[-1]] if pieces[-1] else [])
    first=0
    if lines and lines[0].rstrip(b'\r\n')==b'---':
        for i in range(1,len(lines)):
            if lines[i].rstrip(b'\r\n')==b'---':
                first=i+1
                break
        else:
            return {'error':'UNCLOSED_FRONTMATTER'}
    sections=[]
    fence=None
    for i in range(first,len(lines)):
        text=lines[i].rstrip(b'\r\n')
        marker=FENCE.fullmatch(text)
        if fence is not None:
            if marker and marker[1][0]==fence[0] and len(marker[1])>=len(fence) and not marker[2].strip():
                fence=None
            continue
        if marker and (marker[1][0]!=96 or bytes([96]) not in marker[2]):
            fence=marker[1]
            continue
        heading=HEADING.fullmatch(text)
        if heading and len(heading[1])<=3:
            sections.append((i,len(heading[1])))
            if len(sections)>MAX_SECTIONS:
                return {'error':'SECTION_BUDGET'}
    if fence is not None:
        return {'error':'UNCLOSED_FENCE'}
    result=[]
    for pos,(start, level) in enumerate(sections):
        end=sections[pos+1][0] if pos+1<len(sections) else len(lines)
        if end-start>256:
            return {'error':'SECTION_BUDGET'}
        region=b''.join(lines[start:end])
        locator=dict(source_id=source_id,source_sha=expected_sha,start=start+1,end=end,
                     region_sha=hashlib.sha256(region).hexdigest())
        result.append(dict(level=level, locator=locator))
    return dict(sections=result)
