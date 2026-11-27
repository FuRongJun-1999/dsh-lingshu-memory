"""治理受理判据：只消费受信主体、当前元数据与证据，不访问文件。"""
from framework.api import govern_transition


ACTIONS = frozenset(('forget', 'restore', 'change_policy', 'correct_revision'))


def decide_govern(request, *, context, metadata, verify_restore):
    """调用方须先校验 v2 请求，并在同一锁下提供当前元数据和证明查询。"""
    prefix, _, action = request['kind'].partition('.')
    if prefix != 'Govern' or action not in ACTIONS:
        raise ValueError('INVALID_ARGUMENT')
    if (metadata is None or metadata['tenant'] != context['tenant']
            or context['principal'] not in metadata['creation_readers']
            or context['clearance'] < metadata['declared_sensitivity']):
        raise ValueError('NOT_FOUND_OR_DENIED')
    policy_safe = True
    if action in ('change_policy', 'correct_revision'):
        candidate = request if action == 'change_policy' else request['replacement']
        policy_safe = (candidate['declared_sensitivity'] >= metadata['declared_sensitivity']
                       and set(candidate['reader_ceiling']) <= set(metadata['creation_readers']))
    args = (metadata['state'], metadata['revision'], request['expected_revision'], action, True, policy_safe)
    # 先判权限、版本和状态，才为可恢复修订读取证明。
    allowed = govern_transition(*args, proof_fresh=True)
    if action == 'restore':
        return govern_transition(*args, proof_fresh=verify_restore())
    return allowed
