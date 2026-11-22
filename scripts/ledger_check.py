"""Validate the stage ledger: commits exist, grades are legal, no over-claiming."""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEDGER = ROOT / 'docs' / 'STAGE_LEDGER.md'
ROW = re.compile(r'^\|\s*(stage-[0-9.]+-v\d+)\s*\|\s*([0-9a-f]{40})\s*\|\s*(\d+)\s*\|\s*(I[0-4])\s*\|\s*([A-Z_]+/[A-Z_]+)\s*\|\s*(.+?)\s*\|$')
GRADES = ('I0', 'I1', 'I2', 'I3', 'I4')
GATES = ('NOT_RUN/BLOCK',)
FORBIDDEN = ('production pass', 'production-ready', 'production ready', '生产通过', '生产就绪', '可上线')


def rows(text):
    found = []
    for line in text.splitlines():
        match = ROW.match(line.strip())
        if match:
            found.append({'stage': match.group(1), 'commit': match.group(2), 'tests': int(match.group(3)),
                          'independence': match.group(4), 'gates': match.group(5), 'note': match.group(6)})
    return found


def commit_exists(root, commit):
    result = subprocess.run(['git', 'cat-file', '-e', commit + '^{commit}'], cwd=root,
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    return result.returncode == 0


def is_ancestor(root, older, newer):
    result = subprocess.run(['git', 'merge-base', '--is-ancestor', older, newer], cwd=root,
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    return result.returncode == 0


def main(argv=None):
    root = ROOT
    text = LEDGER.read_text(encoding='utf-8')
    problems = []
    entries = rows(text)
    if not entries:
        problems.append('ledger_empty')
    seen = set()
    for entry in entries:
        if entry['stage'] in seen:
            problems.append('duplicate_stage:' + entry['stage'])
        seen.add(entry['stage'])
        if entry['independence'] not in GRADES:
            problems.append('bad_grade:' + entry['stage'])
        if entry['gates'] not in GATES:
            problems.append('bad_gates:' + entry['stage'])
        if entry['independence'] in ('I0', 'I1'):
            lowered = entry['note'].lower()
            for word in FORBIDDEN:
                if word in lowered:
                    problems.append('overclaim:' + entry['stage'])
        if not commit_exists(root, entry['commit']):
            problems.append('unknown_commit:' + entry['stage'])
    for previous, current in zip(entries, entries[1:]):
        if commit_exists(root, previous['commit']) and commit_exists(root, current['commit']):
            if not is_ancestor(root, previous['commit'], current['commit']):
                problems.append('row_order:' + current['stage'])
    for required in ('## 当前边界声明', '## 已知共因风险'):
        if required not in text:
            problems.append('missing_section:' + required)
    for problem in problems:
        print('FAIL', problem)
    print('STAGE LEDGER:', 'PASS' if not problems else 'FAIL')
    return 0 if not problems else 1


if __name__ == '__main__':
    raise SystemExit(main())