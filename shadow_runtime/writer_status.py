"""Per-instance status, isolated from transaction and principal identity.

Trusted fixture launcher enrolls a unique name once and gives its handle to a
worker privately. Trusted local filesystem and clock; no host discovery or takeover.
"""
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import pathlib
import re
import secrets
from framework.spec import parse
from shadow_runtime.durability import ExclusiveFileLock, atomic_write_text


def _name(s):
    if type(s) is not str or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,63}', s):
        raise ValueError('INVALID_WRITER_ID')
    return s


def _tick(n):
    if type(n) is not int or not 0 <= n < 2**53:
        raise ValueError('INVALID_TICK')
    return n


@dataclass(frozen=True)
class WriterHandle:
    writer_id: str
    credential: str = field(repr=False)


class WriterStatus:
    TTL = 60  # fixture ticks; expiry tick is exclusive

    def __init__(self, root, *, synthetic):
        if synthetic is not True:
            raise ValueError('EXPLICIT_SYNTHETIC_REQUIRED')
        self.directory = pathlib.Path(root) / 'writer-status-v1'

    def _path(self, writer_id):
        key = hashlib.sha256(_name(writer_id).encode()).hexdigest()
        return self.directory / (key + '.json')

    def _load(self, path, writer_id):
        data = parse(path.read_text(encoding='utf-8'))
        if type(data) is not dict or set(data) != {'writer_id','owner_digest','seq','observed','state'}:
            raise ValueError('INVALID_SLOT')
        if data['writer_id'] != writer_id or type(data['owner_digest']) is not str or not re.fullmatch('[0-9a-f]{64}', data['owner_digest']):
            raise ValueError('INVALID_SLOT_OWNER')
        seq = _tick(data['seq'])
        if seq == 0:
            if data['observed'] is not None or data['state'] is not None:
                raise ValueError('INVALID_INITIAL_SLOT')
        elif data['state'] not in ('healthy','degraded'):
            raise ValueError('INVALID_STATE')
        else:
            _tick(data['observed'])
        return data

    def _save(self, path, data):
        atomic_write_text(path, json.dumps(data,sort_keys=True)+'\n',durable=False)

    def enroll(self, writer_id):
        path = self._path(writer_id)
        with ExclusiveFileLock(path.with_suffix('.lock')):
            if path.exists():
                raise ValueError('WRITER_ALREADY_ENROLLED')
            key = secrets.token_hex(32)
            self._save(path, dict(writer_id=writer_id, owner_digest=hashlib.sha256(key.encode()).hexdigest(),
                                  seq=0, observed=None, state=None))
            return WriterHandle(writer_id,key)

    def identify(self, handle):
        """Validate the issuer at store construction without publishing a heartbeat."""
        if type(handle) is not WriterHandle or type(handle.credential) is not str:
            raise ValueError('WRITER_HANDLE_REQUIRED')
        row = self._load(self._path(handle.writer_id), handle.writer_id)
        if not hmac.compare_digest(row['owner_digest'], hashlib.sha256(handle.credential.encode()).hexdigest()):
            raise ValueError('WRITER_MISMATCH')
        return handle.writer_id

    def publish(self, handle, *, state, now):
        _tick(now)
        if type(handle) is not WriterHandle or state not in ('healthy','degraded') or type(handle.credential) is not str:
            raise ValueError('INVALID_PUBLICATION')
        path = self._path(handle.writer_id)
        with ExclusiveFileLock(path.with_suffix('.lock')):
            row = self._load(path, handle.writer_id)
            if not hmac.compare_digest(row['owner_digest'], hashlib.sha256(handle.credential.encode()).hexdigest()):
                raise ValueError('WRITER_MISMATCH')
            if row['observed'] is not None and now < row['observed']:
                raise ValueError('OLDER_OBSERVATION')
            row.update(seq=_tick(row['seq']+1), observed=now, state=state)
            self._save(path,row)
            return dict(writer_id=handle.writer_id,seq=row['seq'])

    def read(self, writer_id, *, now):
        _tick(now)
        try:
            row = self._load(self._path(writer_id), writer_id)
        except (OSError, ValueError, RecursionError):
            return {'state':'unknown'}
        if not row['seq'] or not row['observed'] <= now < row['observed'] + self.TTL:
            return {'state':'unknown'}
        return {k:row[k] for k in ('writer_id','seq','observed','state')}
