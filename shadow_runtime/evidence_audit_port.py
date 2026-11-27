"""合成影子库的证据投影；授权在读取文件库以前判定。"""
from framework.contracts import validate_v2_request
from framework.evidence_audit import evidence_audit
from framework.read_get import ReadSnapshot
from framework.security import context_shape, integer
from shadow_runtime.store import ShadowMarkdownStore, _node_dir_key


def file_evidence_audit(store, request, *, context, now, can_audit, limit):
    if type(store) is not ShadowMarkdownStore or not store.synthetic:
        raise ValueError('SYNTHETIC_FILE_STORE_REQUIRED')
    req = validate_v2_request(request)
    if req['kind'] != 'Read.get' or req['include_provenance']:
        raise ValueError('AUDIT_SELECTOR_REQUIRED')
    if not integer(limit) or not 1 <= limit <= 64:
        raise ValueError('INVALID_AUDIT_LIMIT')
    try:
        actor = context_shape(context)
    except (ValueError, TypeError, RecursionError):
        return {'error':'AUTH_REQUIRED'}
    if not integer(now) or now >= actor['expires_at']:
        return {'error':'AUTH_REQUIRED'}
    if can_audit(actor,req['node_id']) is not True:
        return {'error':'NOT_FOUND_OR_DENIED'}
    with store._lock():
        store._recover_pending_transactions()
        manifest = store._load_manifest_or_init()
        nodes, metadata = store._build_graph_nodes(manifest)
        view = ReadSnapshot(manifest['content_generation'],manifest['policy_generation'],nodes,metadata)

        def proof(key, revision):
            path = store.root / 'verifications' / f'{_node_dir_key(key)}_rev_{revision:06d}.json'
            return store._read_json_strict(path) if path.is_file() else None

        return evidence_audit(req,context=actor,now=now,view=view,model=store.model,
                              can_audit=lambda *_:True,proof=proof,limit=limit)
