"""显式合成任务状态适配，沿用单槽链头比较与原子写入。"""
import json

from framework.spec import parse
from framework.task_progress import decide_task_progress
from shadow_runtime.state_event_port import StateEventStore

SLOT = 'task.progress.v1'


def change_task_progress(store, *, task_id, target, result, expected, context, now, allowed):
    """allowed 必须表示本次任务迁移的读取和写入授权。"""
    if type(store) is not StateEventStore:
        raise ValueError('SYNTHETIC_SLOT_STORE_REQUIRED')
    scope = dict(subject=task_id,slot=SLOT,context=context,now=now,allowed=allowed)
    view = store.inspect(**scope)
    if 'error' in view or view.get('status') == 'unknown':
        return view
    if view.get('status') not in ('active','empty'):
        return {'error':'TASK_STATE_UNKNOWN'}
    if expected != view['checkpoint']:
        return {'error':'STATE_CHANGED'}
    raw = view.get('value')
    try:
        current = None if raw is None else parse(raw)
    except (ValueError,TypeError,RecursionError):
        return {'error':'TASK_STATE_UNKNOWN'}
    if raw is not None and type(current) is not dict:
        return {'error':'TASK_STATE_UNKNOWN'}
    decision = decide_task_progress(current,target=target,result=result)
    if 'error' in decision:
        return decision
    saved = store.append(**scope,expected=expected,old=raw,
                         new=json.dumps(decision,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    return dict(saved,task=decision) if saved.get('status')=='appended' else saved
