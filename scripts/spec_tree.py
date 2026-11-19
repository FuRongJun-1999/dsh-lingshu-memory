"""Read-only inventory check. This lock is outside spec/, so no file excludes itself."""
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framework.spec import parse


def inventory(directory):
    files = {}
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError('spec directory unavailable')
    def fail(error):
        raise error
    for base, dirs, names in os.walk(directory, followlinks=False, onerror=fail):
        for name in dirs + names:
            path = Path(base) / name
            if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 1024:
                raise ValueError('links not in inventory: ' + name)
        for name in names:
            path = Path(base) / name
            if not path.is_file():
                raise ValueError('not a regular file: ' + name)
            files[path.relative_to(directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not files:
        raise ValueError('empty inventory')
    return dict(sorted(files.items()))


def compare(directory, lock):
    if type(lock) is not dict or set(lock) != {'format','algorithm','files','reason'} or type(lock['format']) is not int or lock['format'] != 1 or lock['algorithm'] != 'sha256-bytes' or not isinstance(lock['reason'],str) or not lock['reason'].strip() or not isinstance(lock['files'],dict):
        raise ValueError('invalid spec tree lock')
    expected = lock['files']; actual = inventory(directory)
    return { 'added': sorted(actual.keys()-expected.keys()), 'missing':sorted(expected.keys()-actual.keys()), 'changed':sorted(k for k in actual.keys() & expected.keys() if actual[k]!=expected[k]) }


if __name__ == '__main__':
    try:
        report = compare(ROOT/'spec',parse((ROOT/'scripts/spec-tree.lock.json').read_text(encoding='utf-8')))
        print(json.dumps(report,sort_keys=True)); sys.exit(int(any(report.values())))
    except (OSError, ValueError) as error:
        print(str(error),file=sys.stderr); sys.exit(2)
