"""显式合成文件库的时间窗锚点适配。"""
from framework.read_get import ReadSnapshot
from framework.time_anchors import time_anchors
from shadow_runtime.store import ShadowMarkdownStore


def file_time_anchors(store, *, axis, window_start, window_end, condition_query, limit, context, now):
    if type(store) is not ShadowMarkdownStore or not store.synthetic:
        raise ValueError('SYNTHETIC_FILE_STORE_REQUIRED')
    with store._lock():
        store._recover_pending_transactions()
        manifest = store._load_manifest_or_init()
        nodes, metadata = store._build_graph_nodes(manifest)
        view = ReadSnapshot(manifest['content_generation'], manifest['policy_generation'], nodes, metadata)
        return time_anchors(axis=axis,window_start=window_start,window_end=window_end,
                            condition_query=condition_query,limit=limit,context=context,now=now,view=view,model=store.model)
