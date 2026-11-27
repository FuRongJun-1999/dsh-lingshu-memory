"""只读路由建议：候选与宿主允许的能力名称，不执行工具。"""
import re
from framework.contracts import validate_v2_request
from framework.read_search import read_search

NAME = re.compile(r'[a-z][a-z0-9_.-]{0,63}')
ATTRIBUTE = 'route.capability'


def suggest_route(request, *, context, now, view, postings, body, model, capabilities):
    """可信宿主提供同一快照、身份以及能力白名单。"""
    req = validate_v2_request(request)
    if req['kind'] != 'Read.search' or 'cursor' in req or req['include_provenance']:
        raise ValueError('ROUTE_SELECTOR_REQUIRED')
    if type(capabilities) is not frozenset or len(capabilities) > 256 or any(
            type(x) is not str or NAME.fullmatch(x) is None for x in capabilities):
        raise ValueError('INVALID_CAPABILITY_CATALOG')
    page = read_search(req,context=context,now=now,view=view,postings=postings,body=body,model=model)
    if page.error is not None:
        return {'error':page.error}
    hints = set()
    # 仅当前授权页上的显式声明；不从正文推导，不暴露被截断条目的能力。
    for locator in page.locators:
        attrs = view.metadata[locator['id']]['condition_space']['attributes']
        name = attrs.get(ATTRIBUTE)
        if name in capabilities:
            hints.add(name)
    return dict(candidates=list(page.locators),suggested_capabilities=sorted(hints))
