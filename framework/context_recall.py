"""任务证据选择与交付前复核：只消费显式、受信的搜索和回读端口。"""
import copy


class RecallBlocked(Exception):
    """不交付证据的原因；调用方负责记录和降级。"""


def matches(row, requirement):
    return row is not None and all(row[k] == requirement[k] for k in ("key","architecture","version","conditions"))


def _find(task, requirement, search, get, *, keyed):
    hits = search(task['query'], evidence_key=requirement['key'] if keyed else None, limit=64 if keyed else 4)
    # 触及上限时不能宣称排除了同键冲突。
    if keyed and len(hits) >= 64:
        raise RecallBlocked('CANDIDATE_LIMIT')
    found = []
    for locator in hits:
        row = get(locator)
        if matches(row, requirement):
            found.append(row)
    if len(found) > 1:
        raise RecallBlocked('AMBIGUOUS')
    return found[0] if found else None


def select_evidence(task, *, search, get, refetch):
    """任务须已校验；端口按工作单元执行授权、预算和观测。"""
    selected = []
    for req in task['requirements']:
        row = _find(task, req, search, get, keyed=False)
        if task['budget']['retries']:
            refetch()
            row = _find(task, req, search, get, keyed=True)
        elif row is not None:
            raise RecallBlocked('KEY_CONFIRMATION_REQUIRED')
        if row is None:
            raise RecallBlocked('EVIDENCE_GAP')
        selected.append(row)
    return selected


def revalidate_evidence(task, rows, *, get):
    """必须使用实时回读；失败不返回部分正文。"""
    if len(rows) != len(task['requirements']):
        raise RecallBlocked('EVIDENCE_GAP')
    checked = []
    for old, req in zip(rows, task['requirements']):
        current = get(old['locator'])
        if current != old or not matches(current, req):
            raise RecallBlocked('EVIDENCE_CHANGED')
        checked.append({'body':current['body'], 'citation':copy.deepcopy(current['locator'])})
    return checked
