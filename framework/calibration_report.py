"""授权样本的只读校准差；不写回置信度。"""
import re
from fractions import Fraction
from framework.security import context_shape, integer
from framework.spec import digest


def calibration_report(*, expected_sha, context, now, allowed, snapshot):
    """授权与取样由可信宿主绑定；摘要来自独立发布的样本锚。"""
    if type(expected_sha) is not str or re.fullmatch(r'[0-9a-f]{64}',expected_sha) is None:
        raise ValueError('INVALID_CALIBRATION_DIGEST')
    try:
        actor=context_shape(context)
    except (ValueError,TypeError,RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now>=actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if allowed(actor) is not True:
        return {'error':'NOT_FOUND_OR_DENIED'}
    frame=snapshot(actor)
    if (type(frame) is not dict or set(frame)!={'policy_generation','samples'}
            or not integer(frame['policy_generation']) or type(frame['samples']) is not list
            or len(frame['samples'])>256):
        return {'error':'CALIBRATION_INVALID'}
    if frame['policy_generation']!=actor['policy_generation']:
        return {'error':'POLICY_CHANGED'}
    rows=[]
    pos=neg=total=0
    for row in frame['samples']:
        if (type(row) is not dict or set(row)!={'confidence_bp','positive','negative'}
                or any(not integer(value) for value in row.values()) or row['confidence_bp']>10000
                or row['positive']+row['negative']==0):
            return {'error':'CALIBRATION_INVALID'}
        rows.append(dict(row));pos+=row['positive'];neg+=row['negative'];total+=row['confidence_bp']
    if digest(dict(policy_generation=actor['policy_generation'],samples=rows))!=expected_sha:
        return {'error':'CALIBRATION_CHANGED'}
    expected=Fraction(total,len(rows)*10000) if rows else None
    actual=Fraction(pos,pos+neg) if rows else None
    gap=expected-actual if rows else None
    verdict=('insufficient_data' if not pos else 'overconfident' if gap>0
             else 'underconfident' if gap<0 else 'equal')
    def ratio(value):
        return None if value is None else [value.numerator,value.denominator]
    return dict(samples=len(rows),positive=pos,negative=neg,expected=ratio(expected),actual=ratio(actual),
                gap=ratio(gap),verdict=verdict)
