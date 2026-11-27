"""版本绑定的证明格式和资格判定，不验证生产身份，不访问文件。"""
from framework.model import verification_eligible
from framework.spec import digest


PROOF_FIELDS = {'node_id', 'subject_revision', 'subject_sha', 'verifier_id', 'source_id',
                'scope', 'method_allowed', 'credential_exists', 'credential_time', 'verified_at'}


def _eligible(body, *, revision, content_sha, source_id, required_scope):
    return verification_eligible(
        subject_revision=revision, subject_sha=content_sha,
        proof_revision=body['subject_revision'], proof_sha=body['subject_sha'],
        verifier_id=body['verifier_id'], source_id=source_id,
        scope_covers=body['scope'] in ('full', required_scope),
        method_allowed=body['method_allowed'], credential_exists=body['credential_exists'],
        credential_time=body['credential_time'], verified_at=body['verified_at'],
    )


def issue_proof(*, node_id, revision, content_sha, source_id, verifier_id, scope,
                method_allowed, credential_exists, credential_time, verified_at):
    """调用方须确认当前提交版本、资格和时钟；None 表示不出证。"""
    body = dict(node_id=node_id, subject_revision=revision, subject_sha=content_sha,
                source_id=source_id, verifier_id=verifier_id, scope=scope,
                method_allowed=method_allowed, credential_exists=credential_exists,
                credential_time=credential_time, verified_at=verified_at)
    if not isinstance(node_id, str) or not node_id or scope not in ('full', 'restore') or not _eligible(
            body, revision=revision, content_sha=content_sha, source_id=source_id, required_scope='restore'):
        return None
    return dict(body, proof_sha=digest(body))


def proof_applies(proof, *, node_id, revision, content_sha, source_id, required_scope='restore'):
    """校验封签与完整当前绑定；摘要不是签名，可信证据仍由宿主提供。"""
    if type(proof) is not dict or set(proof) != PROOF_FIELDS | {'proof_sha'}:
        return False
    body = {k:v for k,v in proof.items() if k != 'proof_sha'}
    if digest(body) != proof['proof_sha']:
        return False
    if proof['node_id'] != node_id or proof['source_id'] != source_id or required_scope not in ('full', 'restore'):
        return False
    return _eligible(body, revision=revision, content_sha=content_sha, source_id=source_id, required_scope=required_scope)
