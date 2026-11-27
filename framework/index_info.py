"""已授权索引证据对照；不扫描、不维修。"""
import re
from framework.security import context_shape, integer


def index_info(*, expected_generation, context, now, allowed, snapshot):
    """宿主提供同临界区内、同索引口径的内存与落盘摘要。"""
    if not integer(expected_generation):
        raise ValueError('INVALID_INDEX_GENERATION')
    try:
        actor = context_shape(context)
    except (TypeError, ValueError, RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now>=actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if allowed(actor) is not True:
        return {'error':'INFO_DENIED'}
    frame=snapshot(actor)
    if (type(frame) is not dict or set(frame)!={'policy_generation','memory','disk'}
            or not integer(frame['policy_generation'])):
        return {'error':'INDEX_EVIDENCE_INVALID'}
    if frame['policy_generation']!=actor['policy_generation']:
        return {'error':'POLICY_CHANGED'}
    for side in ('memory','disk'):
        row=frame[side]
        if row is None:
            continue
        if (type(row) is not dict or set(row)!={'generation','node_count','sha256'}
                or not integer(row['generation']) or not integer(row['node_count'])
                or type(row['sha256']) is not str or re.fullmatch(r'[0-9a-f]{64}',row['sha256']) is None):
            return {'error':'INDEX_EVIDENCE_INVALID'}
    memory,disk=frame['memory'],frame['disk']
    if memory is None:
        return {'status':'unknown'}
    if memory['generation']!=expected_generation:
        return {'error':'INDEX_SNAPSHOT_CHANGED'}
    if disk is None:
        return {'status':'unknown'}
    if memory['generation']!=disk['generation']:
        status='generation_mismatch'
    elif (memory['node_count'],memory['sha256'])!=(disk['node_count'],disk['sha256']):
        status='same_generation_mismatch'
    else:
        status='observations_match'
    return dict(scope='index_observations',status=status,memory_count=memory['node_count'],disk_count=disk['node_count'])
