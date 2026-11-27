"""显式合成库的双节点时间比较，沿用事务恢复和锁。"""
from framework.read_get import ReadSnapshot
from framework.time_relation import relate_time
from shadow_runtime.store import ShadowMarkdownStore


def file_time_relation(store, *, a, b, axis, condition_query, context, now):
    if type(store) is not ShadowMarkdownStore or not store.synthetic:
        raise ValueError('SYNTHETIC_FILE_STORE_REQUIRED')
    with store._lock():
        store._recover_pending_transactions()
        manifest = store._load_manifest_or_init()
        nodes, metadata = store._build_graph_nodes(manifest)
        view = ReadSnapshot(manifest['content_generation'], manifest['policy_generation'], nodes, metadata)
        return relate_time(a=a,b=b,axis=axis,condition_query=condition_query,context=context,now=now,view=view,model=store.model)
