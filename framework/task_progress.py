"""受信当前任务状态的纯迁移判据；不访问台账。"""
STATES = frozenset(('active','blocked','done','dropped'))
ALLOWED = {None: {'active'}, 'active': {'blocked','done','dropped'},
           'blocked': {'active','dropped'}, 'done': set(), 'dropped': set()}


def decide_task_progress(current, *, target, result=None):
    """None 是已证实的空任务；不接受未知状态或无结果的完成。"""
    if type(target) is not str or target not in STATES:
        raise ValueError('INVALID_TASK_STATUS')
    if target == 'done':
        if type(result) is not str or not result.strip() or len(result)>512:
            raise ValueError('TASK_RESULT_REQUIRED')
        result.encode('utf-8')
    elif result is not None:
        raise ValueError('TASK_RESULT_NOT_ALLOWED')
    if current is not None and (type(current) is not dict or set(current)!={'status','result'}
            or type(current['status']) is not str or current['status'] not in STATES
            or (current['status']=='done' and (type(current['result']) is not str or not current['result'].strip()))
            or (current['status']!='done' and current['result'] is not None)):
        return {'error':'TASK_STATE_UNKNOWN'}
    if target not in ALLOWED[None if current is None else current['status']]:
        return {'error':'TASK_TRANSITION_REJECTED'}
    return dict(status=target,result=result)
