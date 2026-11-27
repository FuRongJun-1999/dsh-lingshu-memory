"""按已校验 intent 与 manifest 摘要选择方向，不调用磁盘动作。"""
from framework.spec import digest


def decide_recovery(intent, current_manifest):
    """输入来自持锁的校验端口；结果只指示方向，不证明可安全改盘。"""
    state = intent['state']
    if state in ('complete', 'aborted'):
        return 'skip'
    if state != 'prepared':
        raise ValueError('INTEGRITY_FAILURE: invalid transaction state')
    current = digest(current_manifest)
    before = current == intent['before_manifest_sha']
    after = current == intent['after_manifest_sha']
    if before == after:
        raise ValueError('INTEGRITY_FAILURE: transaction manifest diverged or ambiguous')
    return 'rollback' if before else 'rollforward'
