"""Validate the stage ledger: commits exist, grades are legal, no over-claiming.

Kept deliberately small: the checker itself is a trust root, so every failure
branch is covered by tests and the wording oracle is frozen there."""
import re
import subprocess
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / 'docs' / 'STAGE_LEDGER.md'
ROW = re.compile(r'^\|\s*(stage-[0-9.]+-v\d+)\s*\|\s*([0-9a-f]{40})\s*\|\s*(\d+)\s*\|\s*(I[0-4])\s*\|\s*([A-Z_]+/[A-Z_]+)\s*\|\s*(.+?)\s*\|$')
GRADES = ('I0', 'I1', 'I2', 'I3', 'I4')
MAX_GRADE = 'I1'
MIN_ROWS = 8
GATES = ('NOT_RUN/BLOCK',)
FORBIDDEN = ('production pass', 'production approved', 'production-approved', 'production ready',
             'production-ready', 'ga-ready', 'general availability', 'prod-ready', 'release-ready',
             '生产通过', '生产放行', '生产就绪', '生产可用', '可投产', '投产就绪', '可上线', '已上线',
             '可发布', '已独立验证', '已由第三方验证')
DROP = dict.fromkeys(map(ord, '\u200b\u200c\u200d\u2060\ufeff'), None)


def squash(text):
    stripped = unicodedata.normalize('NFKC', text).translate(DROP).casefold()
    return re.sub(r'[^0-9a-z\u3400-\u9fff]+', '', stripped)


FROZEN_FORBIDDEN = tuple(squash(word) for word in FORBIDDEN)


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


def head_commit(root):
    result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root,
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    return result.stdout.strip() if result.returncode == 0 else ''


def check_text(text, root, exists=None, ancestor=None, head=None):
    exists = exists or (lambda commit: commit_exists(root, commit))
    ancestor = ancestor or (lambda older, newer: is_ancestor(root, older, newer))
    head = head if head is not None else head_commit(root)
    problems = []
    entries = rows(text)
    if not entries:
        problems.append('ledger_empty')
    if len(entries) < MIN_ROWS:
        problems.append('too_few_rows')
    seen_stage = set()
    seen_commit = set()
    for entry in entries:
        if entry['stage'] in seen_stage:
            problems.append('duplicate_stage:' + entry['stage'])
        seen_stage.add(entry['stage'])
        if entry['commit'] in seen_commit:
            problems.append('duplicate_commit:' + entry['stage'])
        seen_commit.add(entry['commit'])
        if entry['gates'] not in GATES:
            problems.append('bad_gates:' + entry['stage'])
        if entry['independence'] not in GRADES:
            problems.append('bad_grade:' + entry['stage'])
        elif GRADES.index(entry['independence']) > GRADES.index(MAX_GRADE):
            problems.append('grade_ceiling:' + entry['stage'])
        for word in FROZEN_FORBIDDEN:
            if word and word in squash(entry['note']):
                problems.append('overclaim:' + entry['stage'])
                break
        if not exists(entry['commit']):
            problems.append('unknown_commit:' + entry['stage'])
    for previous, current in zip(entries, entries[1:]):
        if ancestor(previous['commit'], current['commit']) is False:
            problems.append('row_order:' + current['stage'])
    if entries and head and ancestor(entries[-1]['commit'], head) is False:
        problems.append('row_not_in_history:' + entries[-1]['stage'])
    for required in ('## 当前边界声明', '## 已知共因风险'):
        if required not in text:
            problems.append('missing_section:' + required)
    boundary = ''
    if '## 当前边界声明' in text:
        tail = text.split('## 当前边界声明', 1)[1]
        boundary = re.split(r'^## ', tail, maxsplit=1, flags=re.MULTILINE)[0]
    if not boundary.strip():
        problems.append('boundary_empty')
    if 'I1' not in boundary:
        problems.append('boundary_without_ceiling')
    for phrase in ('I2', 'I3', 'I4'):
        if phrase not in boundary:
            problems.append('boundary_missing:' + phrase)
    chain = root / 'scripts' / 'check_all.py'
    chain_text = chain.read_text(encoding='utf-8') if chain.is_file() else ''
    if 'ledger_check.py' not in chain_text:
        problems.append('ledger_not_wired')
    return problems


def main(argv=None):
    text = LEDGER.read_text(encoding='utf-8')
    problems = check_text(text, ROOT)
    for problem in problems:
        print('FAIL', problem)
    print('STAGE LEDGER:', 'PASS' if not problems else 'FAIL')
    print('LEDGER ROWS:', len(rows(text)), '| CEILING:', MAX_GRADE)
    return 0 if not problems else 1


if __name__ == '__main__':
    raise SystemExit(main())