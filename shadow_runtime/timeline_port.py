"""显式合成文件库的只读时间线端口。"""
from framework.read_get import ReadSnapshot
from framework.read_timeline import read_timeline
from shadow_runtime.store import ShadowMarkdownStore


def file_timeline(store, *, axis, point, condition_query, limit, context, now):
    if type(store) is not ShadowMarkdownStore or not store.synthetic:
        raise ValueError('SYNTHETIC_FILE_STORE_REQUIRED')
    with store._lock():
        store._recover_pending_transactions()
        manifest = store._load_manifest_or_init()
        nodes, metadata = store._build_graph_nodes(manifest)
        view = ReadSnapshot(manifest['content_generation'], manifest['policy_generation'], nodes, metadata)
        return read_timeline(axis=axis,point=point,condition_query=condition_query,limit=limit,
                             context=context,now=now,view=view,model=store.model)
