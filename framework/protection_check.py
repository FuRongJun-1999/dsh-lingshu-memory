"""当前修订的显式保护标记投影；不授予写入或遗忘许可。"""
from framework.read_edges import read_edges


def check_protection(request, *, context, now, view, model, flags):
    """flags 是可信宿主提供的同一锁内权威读口，不接受请求自报。"""
    visible = read_edges(request,context=context,now=now,view=view,model=model)
    locator = visible.get('locator')
    if locator is None:
        return visible
    item = flags(locator['id'],locator['revision'])
    if (type(item) is not dict or set(item)!={'locator','protected','immutable'}
            or type(item['locator']) is not dict or item['locator']!=locator
            or type(item['locator']['revision']) is not int
            or type(item['protected']) is not bool or type(item['immutable']) is not bool):
        return {'error':'PROTECTION_UNKNOWN'}
    return dict(locator=locator,protected=item['protected'],immutable=item['immutable'])
