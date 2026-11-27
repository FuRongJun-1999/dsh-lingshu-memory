"""合成文件库状态端口，沿用事务恢复与共享锁。"""
from framework.read_get import ReadSnapshot
from framework.read_status import read_status
from shadow_runtime.store import ShadowMarkdownStore, _node_dir_key


def file_status(store, request, *, context, now):
    """只接受已经建立的合成库，由受信调用者提供主体和时钟。"""
    if type(store) is not ShadowMarkdownStore or not store.synthetic:
        raise ValueError('SYNTHETIC_FILE_STORE_REQUIRED')
    with store._lock():
        store._recover_pending_transactions()
        manifest = store._load_manifest_or_init()
        nodes, meta = store._build_graph_nodes(manifest)
        view = ReadSnapshot(manifest['content_generation'], manifest['policy_generation'], nodes, meta)

        def proof(key, revision):
            path = store.root / 'verifications' / f'{_node_dir_key(key)}_rev_{revision:06d}.json'
            return store._read_json_strict(path) if path.is_file() else None

        return read_status(request, context=context, now=now, view=view, model=store.model, proof=proof)
