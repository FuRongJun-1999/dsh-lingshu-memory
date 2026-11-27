"""单槽追加事件投影。授权与链头来自可信调用方，不从事件自证。"""
from framework.api import _json_domain
from framework.security import context_shape, integer
from framework.spec import digest


FIELDS = {'subject', 'slot', 'seq', 'recorded_at', 'old', 'new', 'previous_sha'}


def project_state_chain(*, subject, slot, context, now, allowed, checkpoint, events):
    """只处理一个完整槽位；不扫描其他槽，不返回历史值。"""
    for label in (subject, slot):
        if type(label) is not str or not label.strip() or len(label) > 128:
            raise ValueError('INVALID_SLOT_SELECTOR')
        label.encode('utf-8')
    try:
        actor = context_shape(context)
    except (ValueError, TypeError, RecursionError):
        return {'error': 'AUTH_REQUIRED'}
    if not integer(now) or now >= actor['expires_at']:
        return {'error': 'AUTH_REQUIRED'}
    if allowed(actor, subject, slot) is not True:
        return {'error': 'NOT_FOUND_OR_DENIED'}

    # 链头须独立于事件输入，并绑定授权上下文；不能由读取端从截断事件生成。
    head = checkpoint(actor, subject, slot)
    if head is None:
        return {'status': 'unknown', 'reason': 'NO_CHECKPOINT'}
    if (type(head) is not dict or set(head) != {'seq', 'sha'} or not integer(head['seq'])
            or type(head['sha']) is not str or len(head['sha']) != 64
            or any(c not in '0123456789abcdef' for c in head['sha'])):
        return {'error': 'INVALID_CHECKPOINT'}
    if head['seq'] > 4096:
        return {'status': 'unknown', 'reason': 'CHAIN_BUDGET'}
    current, previous_time, previous_sha = None, 0, '0' * 64
    position, recorded_at = 0, None
    for row in events(actor, subject, slot):
        position += 1
        if position > head['seq'] or type(row) is not dict or set(row) != FIELDS:
            return {'error': 'CHAIN_CONFLICT'}
        if (row['subject'] != subject or row['slot'] != slot or not integer(row['seq']) or row['seq'] != position
                or not integer(row['recorded_at']) or not previous_time <= row['recorded_at'] <= now
                or row['previous_sha'] != previous_sha or row['old'] != current):
            return {'error': 'CHAIN_CONFLICT'}
        value = row['new']
        if value is not None and (type(value) is not str or not value.strip() or len(value) > 4096):
            return {'error': 'CHAIN_CONFLICT'}
        try:
            _json_domain(row)
            previous_sha = digest(row)
        except (ValueError, TypeError, RecursionError):
            return {'error': 'CHAIN_CONFLICT'}
        current = value
        previous_time = recorded_at = row['recorded_at']
    if position != head['seq'] or previous_sha != head['sha']:
        return {'error': 'CHAIN_CONFLICT'}
    if not position:
        return {'status': 'empty'}
    if current is None:
        return {'status': 'retired', 'seq': position, 'recorded_at': recorded_at}
    return {'status': 'active', 'value': current, 'seq': position, 'recorded_at': recorded_at}
