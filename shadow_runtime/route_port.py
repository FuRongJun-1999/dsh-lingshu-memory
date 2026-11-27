"""显式合成库的路由建议端口，不连宿主工具执行器。"""
from framework.read_get import ReadSnapshot
from framework.route_candidates import suggest_route
from shadow_runtime.store import ShadowMarkdownStore


def file_route(store, request, *, context, now, capabilities):
    if type(store) is not ShadowMarkdownStore or not store.synthetic:
        raise ValueError('SYNTHETIC_FILE_STORE_REQUIRED')
    with store._lock():
        store._recover_pending_transactions()
        manifest = store._load_manifest_or_init()
        nodes, metadata = store._build_graph_nodes(manifest)
        view = ReadSnapshot(manifest['content_generation'],manifest['policy_generation'],nodes,metadata)
        index = store._load_valid_index(manifest)

        def body(key, revision):
            return store._md_path(key,revision).read_bytes().decode('utf-8')

        return suggest_route(request,context=context,now=now,view=view,postings=index['inverted'] if index else None,
                             body=body,model=store.model,capabilities=capabilities)
