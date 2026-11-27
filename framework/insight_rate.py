"""授权窗口内洞察裁决率，不判全层质量。"""
import re
from fractions import Fraction
from framework.security import context_shape, integer
from framework.spec import digest


def insight_rate(*, expected_sha, since, minimum, context, now, allowed, snapshot):
    """宿主提供已逐条授权的快照及独立固定摘要。"""
    if (type(expected_sha) is not str or re.fullmatch(r'[0-9a-f]{64}',expected_sha) is None
            or not integer(since) or not integer(minimum) or not 1<=minimum<=256):
        raise ValueError('INVALID_INSIGHT_SELECTOR')
    try:
        actor=context_shape(context)
    except (ValueError,TypeError,RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now>=actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if since>now:
        raise ValueError('INVALID_INSIGHT_WINDOW')
    if allowed(actor) is not True:
        return {'error':'INSIGHT_DENIED'}
    frame=snapshot(actor)
    if (type(frame) is not dict or set(frame)!={'policy_generation','events'}
            or not integer(frame['policy_generation']) or type(frame['events']) is not list
            or len(frame['events'])>256):
        return {'error':'INSIGHT_INVALID'}
    if frame['policy_generation']!=actor['policy_generation']:
        return {'error':'POLICY_CHANGED'}
    counts=dict(verified=0,falsified=0,pending=0); rows=[];seen=set()
    for row in frame['events']:
        if (type(row) is not dict or set(row)!={'id','recorded_at','state'}
                or type(row['id']) is not str or re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}',row['id']) is None
                or row['id'] in seen or not integer(row['recorded_at']) or row['recorded_at']>now
                or type(row['state']) is not str or row['state'] not in counts):
            return {'error':'INSIGHT_INVALID'}
        seen.add(row['id']); rows.append(dict(row))
        if row['recorded_at']>=since:
            counts[row['state']]+=1
    if digest(dict(policy_generation=actor['policy_generation'],events=rows))!=expected_sha:
        return {'error':'INSIGHT_CHANGED'}
    n=counts['verified']+counts['falsified']
    if n<minimum:
        return dict(counts,decided=n,status='insufficient',rate=None)
    rate=Fraction(counts['verified'],n)
    return dict(counts,decided=n,status='measured',rate=[rate.numerator,rate.denominator])
