"""合成文件库的出边端口，固定在原有共享锁内。"""
from framework.read_edges import read_edges
from framework.read_get import ReadSnapshot
from shadow_runtime.store import ShadowMarkdownStore


def file_edges(store, request, *, context, now):
    if type(store) is not ShadowMarkdownStore or not store.synthetic:
        raise ValueError('SYNTHETIC_FILE_STORE_REQUIRED')
    with store._lock():
        store._recover_pending_transactions()
        manifest = store._load_manifest_or_init()
        nodes, metadata = store._build_graph_nodes(manifest)
        view = ReadSnapshot(manifest['content_generation'], manifest['policy_generation'], nodes, metadata)
        return read_edges(request, context=context, now=now, view=view, model=store.model)
