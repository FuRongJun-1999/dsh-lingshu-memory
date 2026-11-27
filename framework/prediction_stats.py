"""已授权反馈的预测统计，不跑预测或改阈值。"""
import re
from fractions import Fraction
from framework.security import context_shape, integer
from framework.spec import digest


def prediction_stats(*, expected_sha, context, now, allowed, snapshot):
    """可信宿主逐条授权样本，独立提供完整快照摘要。"""
    if type(expected_sha) is not str or re.fullmatch(r'[0-9a-f]{64}',expected_sha) is None:
        raise ValueError('INVALID_FEEDBACK_SELECTOR')
    try:
        actor=context_shape(context)
    except (TypeError,ValueError,RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now>=actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if allowed(actor) is not True:
        return {'error':'FEEDBACK_DENIED'}
    frame=snapshot(actor)
    if (type(frame) is not dict or set(frame)!={'policy_generation','feedback'}
            or not integer(frame['policy_generation']) or type(frame['feedback']) is not list
            or len(frame['feedback'])>256):
        return {'error':'FEEDBACK_INVALID'}
    if frame['policy_generation']!=actor['policy_generation']:
        return {'error':'POLICY_CHANGED'}
    seen=set();rows=[];hits=0
    for item in frame['feedback']:
        if (type(item) is not dict or set(item)!={'prediction','hit'}
                or type(item['prediction']) is not str
                or re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}',item['prediction']) is None
                or item['prediction'] in seen or type(item['hit']) is not bool):
            return {'error':'FEEDBACK_INVALID'}
        seen.add(item['prediction']);rows.append(dict(item));hits+=item['hit']
    if digest(dict(policy_generation=actor['policy_generation'],feedback=rows))!=expected_sha:
        return {'error':'FEEDBACK_CHANGED'}
    if not rows:
        return dict(status='insufficient',feedback_samples=0,hits=0,hit_rate=None)
    ratio=Fraction(hits,len(rows))
    return dict(status='measured',feedback_samples=len(rows),hits=hits,hit_rate=[ratio.numerator,ratio.denominator])
