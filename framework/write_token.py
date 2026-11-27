"""写入幂等裁决；受信调用方负责请求校验、作用域和锁。"""
from dataclasses import dataclass

from framework.api import retry_action
from framework.model import request_fingerprint


@dataclass(frozen=True)
class WriteDecision:
    action: str
    fingerprint: str


def decide_write(request, *, token, token_corrupt, intent, intent_corrupt):
    """消费同一锁内的证据；不查库、不构造提交证明。"""
    if request['kind'] not in ('Write.create', 'Write.modify'):
        raise ValueError('WRITE_REQUIRED')
    if type(token_corrupt) is not bool or type(intent_corrupt) is not bool:
        raise ValueError('EVIDENCE_FLAGS_REQUIRED')
    fp = request_fingerprint(request)
    if token_corrupt or (token is None and intent_corrupt):
        return WriteDecision('integrity_failure', fp)
    if token is None:
        if intent is None:
            return WriteDecision('first_apply_candidate', fp)
        return WriteDecision('query_only' if intent['fingerprint'] == fp else 'conflict', fp)
    same = token['fingerprint'] == fp or (token['fingerprint'] is None and token['negative_basis'] == 'durable_cancel')
    action = retry_action(token['commit_status'], same, token['history_complete'], token['negative_basis'])
    if action not in ('return_original', 'return_original_cancel', 'conflict'):
        # 未评定、历史缺口或外部负证据都不能授予这个接口首次写入资格。
        action = 'query_only'
    return WriteDecision(action, fp)
