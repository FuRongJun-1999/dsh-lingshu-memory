"""显式合成库的单节点时间检查，沿用共享事务锁。"""
from framework.read_get import ReadSnapshot
from framework.time_consistency import check_time
from shadow_runtime.store import ShadowMarkdownStore


def file_time_check(store, *, node_id, axis, point, condition_query, context, now):
    if type(store) is not ShadowMarkdownStore or not store.synthetic:
        raise ValueError('SYNTHETIC_FILE_STORE_REQUIRED')
    with store._lock():
        store._recover_pending_transactions()
        manifest = store._load_manifest_or_init()
        nodes, metadata = store._build_graph_nodes(manifest)
        view = ReadSnapshot(manifest['content_generation'],manifest['policy_generation'],nodes,metadata)
        return check_time(node_id=node_id,axis=axis,point=point,condition_query=condition_query,
                          context=context,now=now,view=view,model=store.model)
