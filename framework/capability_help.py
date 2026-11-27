"""从受信公开图按需披露能力条件；不加载或执行图中入口。"""
import copy
import re

from framework.security import integer
from framework.spec import digest

ID = re.compile(r'[a-z][a-z0-9]*(?:[._][a-z0-9]+)*')
FIELDS = ('id','name','state','conditions','subfunctions','execution','negative','dependencies')


def capability_help(graph, *, expected_sha, capability=None, limit=16):
    """expected_sha 来自受信发布物；查询者不能替换图或摘要。"""
    if not integer(limit) or not 1 <= limit <= 64:
        raise ValueError('INVALID_HELP_LIMIT')
    if capability is not None and (type(capability) is not str or len(capability)>128 or ID.fullmatch(capability) is None):
        raise ValueError('INVALID_CAPABILITY_ID')
    if type(expected_sha) is not str or re.fullmatch(r'[0-9a-f]{64}',expected_sha) is None or digest(graph) != expected_sha:
        return {'error':'CATALOG_CHANGED'}
    entries = {row['id']:row for row in graph['capabilities'] if row['state']=='isolated'}
    if capability is not None and capability not in entries:
        return {'error':'CAPABILITY_NOT_FOUND'}
    keys = [capability] if capability is not None else sorted(entries)[:limit]
    items = [copy.deepcopy({k:entries[key][k] for k in FIELDS}) for key in keys]
    return dict(scope='isolated_catalog',runtime_ready=False,items=items)
