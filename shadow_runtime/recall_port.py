"""受控文件库取用端口：仅消费显式的合成库，不发现运行环境。"""
import copy

from framework.context_recall import RecallBlocked
from framework.contracts import extract_condition_space, validate_v2_request
from framework.read_get import ReadSnapshot, read_get
from framework.read_search import read_search
from framework.spec import digest
from sandbox_runtime.controller import AlertSink, Controller, RecallPorts
from sandbox_runtime.store import Probe
from shadow_runtime.store import ShadowMarkdownStore

IDENTITY = {'key': 'memory.key', 'architecture': 'memory.architecture', 'version': 'memory.version'}


class FileRecallPort:
    """在单次取用中固定清单摘要；所有检查在共享库锁内完成。"""
    def __init__(self, store, probe, *, condition_query, time_axis, time_point):
        self.store, self.probe = store, probe
        request = validate_v2_request(dict(kind='Read.get', node_id='fixture', include_provenance=False,
                                           condition_query=condition_query, time_axis=time_axis, time_point=time_point))
        if extract_condition_space(request['condition_query'])['attributes']:
            raise ValueError('RECALL_QUERY_ATTRIBUTES_REQUIRED_EMPTY')
        self.query = {k: request[k] for k in ('include_provenance','condition_query','time_axis','time_point')}
        self.anchor = None

    def _snapshot(self, actor):
        self.store._recover_pending_transactions()
        manifest = self.store._load_manifest_or_init()
        signature = digest(manifest)
        if (self.anchor is not None and signature != self.anchor) or manifest['policy_generation'] != actor['policy_generation']:
            raise RecallBlocked('CONTEXT_CHANGED')
        self.anchor = signature
        nodes, metadata = self.store._build_graph_nodes(manifest)
        return manifest, ReadSnapshot(manifest['content_generation'], manifest['policy_generation'], nodes, metadata)

    def _body(self, key, revision):
        return self.store._md_path(key, revision).read_bytes().decode('utf-8')

    def _record(self, operation, argument, options, result, request_id, **fields):
        self.probe.record(operation, request_id=request_id, argument_sha=digest(dict(argument=argument,options=options)),
                          result_sha=digest(result), **fields)

    def search(self, query, actor, now, *, evidence_key=None, limit=8, request_id=None):
        with self.store._lock():
            manifest, view = self._snapshot(actor)
            if evidence_key is None:
                idx = self.store._load_valid_index(manifest)
                page = read_search(dict(self.query,kind='Read.search',query=query,limit=limit), context=actor,
                                   now=now, view=view, postings=idx['inverted'] if idx is not None else None,
                                   body=self._body, model=self.store.model)
                if page.error:
                    raise RecallBlocked(page.error)
                result = list(page.locators)
            else:
                result = []
                for key, node in sorted(view.nodes.items()):
                    attrs = view.metadata[key]['condition_space']['attributes']
                    if attrs.get(IDENTITY['key']) != evidence_key or not self.store.model.can_read(
                            key, view.nodes, tenant=actor['tenant'], principal=actor['principal'], clearance=actor['clearance']):
                        continue
                    result.append(dict(id=key, revision=node.revision, content_sha=node.content_sha))
                    if len(result) == limit:
                        break  # 调用者在触及上限时整批拒绝。
            self._record('search', query, dict(evidence_key=evidence_key,limit=limit), result, request_id,
                         returned=len(result), mode='key' if evidence_key is not None else 'text')
            return result

    def validate(self, actor, now):
        with self.store._lock():
            self._snapshot(actor)

    def get(self, locator, actor, now, *, request_id=None):
        with self.store._lock():
            _, view = self._snapshot(actor)
            key = locator['id']
            node = view.nodes.get(key)
            if node is not None and (node.revision, node.content_sha) != (locator['revision'], locator['content_sha']):
                raise RecallBlocked('EVIDENCE_CHANGED')
            out = read_get(dict(self.query,kind='Read.get',node_id=key), context=actor, now=now, request_id=request_id,
                           snapshot=lambda:view, body=self._body, model=self.store.model,
                           current_context=lambda:actor, current_now=lambda:now)
            if out['error_code'] not in (None, 'NOT_FOUND_OR_DENIED'):
                raise RecallBlocked(out['error_code'])
            row = None
            if out['records']:
                record, = out['records']
                if record['locator'] != locator:
                    raise RecallBlocked('EVIDENCE_CHANGED')
                attrs = view.metadata[key]['condition_space']['attributes']
                if all(k in attrs for k in IDENTITY.values()):
                    row = dict(locator=copy.deepcopy(locator), body=record['body'],
                               conditions={k:v for k,v in attrs.items() if k not in IDENTITY.values()},
                               **{k:attrs[v] for k,v in IDENTITY.items()})
            self._record('get', locator, {}, row, request_id, matched=row is not None,
                         bytes=len(row['body'].encode('utf-8')) if row else 0)
            return row


def recall_file(store, task, *, context_provider, clock, condition_query, time_axis, time_point):
    """在调用方已指定的合成影子库中执行一轮任务；不修改契约或接入宿主。"""
    if type(store) is not ShadowMarkdownStore or not store.synthetic:
        raise ValueError('SYNTHETIC_FILE_STORE_REQUIRED')
    probe, alerts = Probe(), AlertSink()
    port = FileRecallPort(store, probe, condition_query=condition_query, time_axis=time_axis, time_point=time_point)
    controller = Controller(RecallPorts(port.search, port.get, probe, port.validate), probe,
                            context_provider=context_provider, clock=clock, alerts=alerts)
    output = controller.run(task)
    return dict(output=output, actions=probe.events, alerts=alerts.events)
