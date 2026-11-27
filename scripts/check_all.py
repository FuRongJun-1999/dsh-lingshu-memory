"""Run all local specification gates with explicit UTF-8 subprocesses."""
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')

COMMANDS = [
    [sys.executable, '-B', 'scripts/spec_tools.py', 'check'],
    [sys.executable, '-B', 'scripts/spec_tree.py'],
    [sys.executable, '-B', 'scripts/capability_graph.py'],
    [sys.executable, '-B', 'scripts/memory_migration_status.py'],
    [sys.executable, '-B', 'scripts/ledger_check.py'],
    [sys.executable, '-B', 'scripts/release_gate.py'],
    [sys.executable, '-B', 'scripts/migration_gate.py'],
    [sys.executable, '-B', 'scripts/workspace_index.py'],
    [sys.executable, '-B', 'scripts/public_guard.py'],
    [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
]


def main():
    failures = 0
    for argv in COMMANDS:
        result = subprocess.run(argv, cwd=ROOT, env=ENV, shell=False, capture_output=True,
                                text=True, encoding='utf-8', errors='replace')
        print('GATE', ' '.join(argv[1:]), 'EXIT', result.returncode)
        print(result.stdout, end='')
        print(result.stderr, end='')
        failures += result.returncode != 0
    print('SPECIFICATION TOOLS:', 'PASS' if not failures else 'FAIL')
    print('PRODUCTION RUNTIME GATES: NOT_RUN (isolated synthetic stores are not production acceptance)')
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())