"""单槽原子事件快照；可信合成目录，不是旧 JSONL 或生产存储。"""
import json
from pathlib import Path

from framework.security import context_shape, integer
from framework.spec import digest, parse
from framework.state_chain import project_state_chain
from shadow_runtime.durability import ExclusiveFileLock, atomic_write_text

EMPTY = {'seq': 0, 'sha': '0' * 64}
MAX_EVENTS = 4096
MAX_FILE_BYTES = 160 * 1024 * 1024


class StateEventStore:
    def __init__(self, root, *, synthetic):
        if synthetic is not True:
            raise ValueError('EXPLICIT_SYNTHETIC_REQUIRED')
        self.root = Path(root).resolve() / 'slot-events-v1'

    @staticmethod
    def _selector(subject, slot):
        for text in (subject,slot):
            if type(text) is not str or not text.strip() or len(text)>128:
                raise ValueError('INVALID_SLOT_SELECTOR')
            text.encode('utf-8')

    def _path(self, tenant, subject, slot):
        return self.root / (digest([tenant,subject,slot]) + '.json')

    @staticmethod
    def _load(path, tenant, subject, slot):
        try:
            with path.open('rb') as stream:
                raw = stream.read(MAX_FILE_BYTES + 1)
        except FileNotFoundError:
            return {'scope':[tenant,subject,slot], 'checkpoint':dict(EMPTY), 'events':[]}
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError('CHAIN_CONFLICT')
        obj = parse(raw.decode('utf-8'))
        if (type(obj) is not dict or set(obj) != {'scope','checkpoint','events'}
                or obj['scope'] != [tenant,subject,slot] or type(obj['events']) is not list
                or len(obj['events']) > MAX_EVENTS):
            raise ValueError('CHAIN_CONFLICT')
        return obj

    @staticmethod
    def _actor(context, now):
        actor = context_shape(context)
        if not integer(now) or now >= actor['expires_at']:
            raise ValueError('AUTH_REQUIRED')
        return actor

    @staticmethod
    def _project(obj, actor, subject, slot, now):
        # 权限在真正访问磁盘前判断；此处只消费该临界区已授权的单槽证据。
        return project_state_chain(subject=subject,slot=slot,context=actor,now=now,allowed=lambda *_:True,
                                   checkpoint=lambda *_:obj['checkpoint'],events=lambda *_:iter(obj['events']))

    def inspect(self, *, subject, slot, context, now, allowed):
        self._selector(subject,slot)
        actor = self._actor(context,now)
        if allowed(actor,subject,slot) is not True:
            return {'error':'NOT_FOUND_OR_DENIED'}
        path = self._path(actor['tenant'],subject,slot)
        with ExclusiveFileLock(path.with_suffix('.lock')):
            try:
                data = self._load(path,actor['tenant'],subject,slot)
                out = self._project(data,actor,subject,slot,now)
            except (OSError,ValueError,TypeError,RecursionError):
                return {'error':'CHAIN_CONFLICT'}
            return dict(out,checkpoint=data['checkpoint']) if out.get('status') in ('active','retired','empty') else out

    def append(self, *, subject, slot, context, now, allowed, expected, old, new):
        """expected 是调用方先前读取的可信链头，不接受自己申报 seq 或时间。"""
        self._selector(subject,slot)
        actor = self._actor(context,now)
        if allowed(actor,subject,slot) is not True:
            return {'error':'NOT_FOUND_OR_DENIED'}
        for value in (old,new):
            if value is not None and (type(value) is not str or not value.strip() or len(value)>4096):
                raise ValueError('INVALID_SLOT_VALUE')
            if value is not None:
                value.encode('utf-8')
        if old is None and new is None:
            raise ValueError('EMPTY_STATE_EVENT')
        if (type(expected) is not dict or set(expected) != {'seq','sha'} or not integer(expected['seq'])
                or type(expected['sha']) is not str or len(expected['sha'])!=64
                or any(c not in '0123456789abcdef' for c in expected['sha'])):
            raise ValueError('INVALID_EXPECTED_CHECKPOINT')
        path = self._path(actor['tenant'],subject,slot)
        with ExclusiveFileLock(path.with_suffix('.lock')):
            try:
                snapshot = self._load(path,actor['tenant'],subject,slot)
                current = self._project(snapshot,actor,subject,slot,now)
            except (OSError,ValueError,TypeError,RecursionError):
                return {'error':'CHAIN_CONFLICT'}
            if current.get('status') not in ('active','retired','empty'):
                return current
            head = snapshot['checkpoint']
            if expected != head or current.get('value') != old:
                return {'error':'STATE_CHANGED'}
            if head['seq'] >= MAX_EVENTS:
                return {'status':'unknown','reason':'CHAIN_BUDGET'}
            row = dict(subject=subject,slot=slot,seq=head['seq']+1,recorded_at=now,old=old,new=new,
                       previous_sha=head['sha'])
            new_head = dict(seq=row['seq'],sha=digest(row))
            unified = dict(snapshot,checkpoint=new_head,events=[*snapshot['events'],row])
            # 存储为单文件快照，逻辑只追加；不声称物理追加或断电持久。
            atomic_write_text(path,json.dumps(unified,ensure_ascii=False,sort_keys=True)+chr(10),durable=False)
            return {'status':'appended','checkpoint':new_head}


def append_state_event(store, **request):
    """已显式初始化的合成库入口，不查找默认目录。"""
    if type(store) is not StateEventStore:
        raise ValueError('SYNTHETIC_SLOT_STORE_REQUIRED')
    return store.append(**request)
