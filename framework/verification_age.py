"""长期未建立当前验证证明的只读诊断。"""
from framework.read_status import read_status
from framework.security import integer


def inspect_verification_age(request, *, context, now, view, model, proof, metadata, min_days):
    """metadata 是受信同快照元数据，按精确定位符查当前修订起始秒。"""
    if not integer(min_days) or not 1<=min_days<=3650:
        raise ValueError('INVALID_SCRUB_AGE')
    selected=read_status(request,context=context,now=now,view=view,model=model,proof=proof)
    locator=selected.get('locator')
    if locator is None:
        return selected
    key=(locator['id'],locator['revision'],locator['content_sha'])
    row=metadata(key)
    if (type(row) is not dict or set(row)!={'key','layer','created_at'} or row['key']!=key
            or type(row['layer']) is not str or row['layer'] not in ('anchor','structural','knowledge','contextual','self')
            or not integer(row['created_at']) or row['created_at']>now):
        return {'error':'SCRUB_METADATA_UNKNOWN'}
    due=now-row['created_at']>=min_days*86400
    findings=[]
    if row['layer']=='knowledge' and due and selected['status']=='unverified':
        findings.append('CURRENT_PROOF_NOT_ESTABLISHED')
    return dict(locator=locator,findings=findings)
