"""Validate the stage ledger: commits exist, grades are legal, no over-claiming.

Kept deliberately small: the checker itself is a trust root, so every failure
branch is covered by tests and the wording oracle is frozen there."""
import re
import subprocess
from itertools import chain
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / 'docs' / 'STAGE_LEDGER.md'
ROW = re.compile(r'^\|\s*(stage-[0-9.]+-v\d+)\s*\|\s*([0-9a-f]{40})\s*\|\s*(\d+)\s*\|\s*(I[0-4])\s*\|\s*([A-Z_]+/[A-Z_]+)\s*\|\s*(.+?)\s*\|$')
GRADES = ('I0', 'I1', 'I2', 'I3', 'I4')
MAX_GRADE = 'I1'
MIN_ROWS = 12
MAX_LAG = 6
CHECKER_STAGE = 10
GATES = ('NOT_RUN/BLOCK',)
FORBIDDEN = ('production pass', 'production approved', 'production-approved', 'production ready',
             'production-ready', 'ga-ready', 'general availability', 'prod-ready', 'release-ready',
             '生产通过', '生产就绪', '生产可用', '可投产', '投产就绪', '可上线', '已上线',
             '可发布', '已独立验证', '已由第三方验证')
CONFUSABLES = str.maketrans({
    chr(0x0430): 'a', chr(0x0435): 'e', chr(0x043e): 'o', chr(0x0440): 'p',
    chr(0x0441): 'c', chr(0x0443): 'y', chr(0x0445): 'x', chr(0x0456): 'i',
    chr(0x0455): 's', chr(0x04cf): 'l', chr(0x0501): 'd', chr(0x03bd): 'v',
    chr(0x03bf): 'o', chr(0x03b1): 'a', chr(0x03c1): 'p', chr(0x03c7): 'x',
})
DROP = dict.fromkeys(map(ord, '\u200b\u200c\u200d\u2060\ufeff'), None)


def squash(text):
    stripped = unicodedata.normalize('NFKC', text).translate(DROP).casefold()
    stripped = stripped.translate(CONFUSABLES)
    return re.sub(r'[^0-9a-z\u3400-\u9fff]+', '', stripped)


FROZEN_FORBIDDEN = tuple(squash(word) for word in FORBIDDEN)
DROPPED_FORBIDDEN = tuple(squash(word) for word in ('生产放行', '已经生产可用', '可投入使用'))
NEGATION = tuple(squash(word) for word in ('不', '未', '非', '禁止', '不得', '不等于', '而不是', '未完成', '仍为', 'not', 'no', 'never'))


def rows(text):
    found = []
    for line in text.splitlines():
        match = ROW.match(line.strip())
        if match:
            found.append({'stage': match.group(1), 'commit': match.group(2), 'tests': int(match.group(3)),
                          'independence': match.group(4), 'gates': match.group(5), 'note': match.group(6)})
    return found


def malformed_rows(text):
    bad = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith('| stage-'):
            continue
        if not ROW.match(stripped):
            bad.append(stripped[:80])
    return bad


def commit_exists(root, commit):
    result = subprocess.run(['git', 'cat-file', '-e', commit + '^{commit}'], cwd=root,
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    return result.returncode == 0


def is_ancestor(root, older, newer):
    result = subprocess.run(['git', 'merge-base', '--is-ancestor', older, newer], cwd=root,
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    return result.returncode == 0


def artifact_present(root, commit, path):
    result = subprocess.run(['git', 'cat-file', '-e', commit + ':' + path], cwd=root,
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    return result.returncode == 0


def commits_behind(root, commit):
    result = subprocess.run(['git', 'rev-list', '--count', commit + '..HEAD'], cwd=root,
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip() or '0')
    except ValueError:
        return None


def head_commit(root):
    result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root,
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    return result.stdout.strip() if result.returncode == 0 else ''


def scan_docs(root):
    problems = []
    files = sorted(list((root / 'docs').glob('*.md')) + list(root.glob('*.md')))
    for path in files:
        if path.name == 'STAGE_LEDGER.md':
            continue
        text = path.read_text(encoding='utf-8')
        for token in DROPPED_FORBIDDEN:
            if token and token in squash(text):
                problems.append('dropped_token:' + path.name)
        for number, line in enumerate(text.splitlines(), 1):
            squashed = squash(line)
            hit = [word for word in chain(FROZEN_FORBIDDEN, DROPPED_FORBIDDEN) if word in squashed]
            if not hit:
                continue
            exempt = False
            for word in hit:
                position = squashed.index(word) if word in squashed else -1
                if position > 0 and any(neg in squashed[:position] for neg in NEGATION):
                    exempt = True
            if exempt:
                continue
            problems.append('doc_overclaim:' + path.name + ':' + str(number))
    return problems

def stage_number(stage):
    match = re.search(r'-v([0-9]+)$', stage)
    return int(match.group(1)) if match else 0


def check_text(text, root, exists=None, ancestor=None, head=None, artifact=None, lag=None, checker=None):
    exists = exists or (lambda commit: commit_exists(root, commit))
    ancestor = ancestor or (lambda older, newer: is_ancestor(root, older, newer))
    head = head if head is not None else head_commit(root)
    artifact = artifact or (lambda commit: artifact_present(root, commit, 'scripts/stage_gate.py'))
    checker_artifact = checker or (lambda commit: artifact_present(root, commit, 'scripts/ledger_check.py'))
    lag = lag or (lambda commit: commits_behind(root, commit))
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
        note_squashed = squash(entry['note'])
        for word in chain(FROZEN_FORBIDDEN, DROPPED_FORBIDDEN):
            if word and word in note_squashed:
                problems.append('overclaim:' + entry['stage'])
                break
        if not exists(entry['commit']):
            problems.append('unknown_commit:' + entry['stage'])
        elif not artifact(entry['commit']):
            problems.append('missing_artifact:' + entry['stage'])
        elif stage_number(entry['stage']) >= CHECKER_STAGE and not checker_artifact(entry['commit']):
            problems.append('missing_checker:' + entry['stage'])
        if entry['tests'] <= 0:
            problems.append('tests_not_positive:' + entry['stage'])
    for previous, current in zip(entries, entries[1:]):
        if ancestor(previous['commit'], current['commit']) is False:
            problems.append('row_order:' + current['stage'])
        if current['tests'] < previous['tests']:
            problems.append('tests_not_monotonic:' + current['stage'])
    if entries and head and ancestor(entries[-1]['commit'], head) is not True:
        problems.append('row_not_in_history:' + entries[-1]['stage'])
    if entries:
        behind = lag(entries[-1]['commit'])
        if behind is None:
            problems.append('git_unavailable')
        elif behind > MAX_LAG:
            problems.append('ledger_stale:{} commits behind'.format(behind))
    for bad in malformed_rows(text):
        problems.append('ledger_row_malformed:' + bad)
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
    chain_file = root / 'scripts' / 'check_all.py'
    chain_text = chain_file.read_text(encoding='utf-8') if chain_file.is_file() else ''
    if 'ledger_check.py' not in chain_text:
        problems.append('ledger_not_wired')
    anchors = root / 'docs' / 'EXTERNAL_ANCHORS.md'
    if not anchors.is_file():
        problems.append('missing_anchor_doc')
    else:
        anchor_text = anchors.read_text(encoding='utf-8')
        for grade in ('## I2', '## I3', '## I4'):
            if grade not in anchor_text:
                problems.append('anchor_section_missing:' + grade.strip('# '))
        if '不允许' not in anchor_text:
            problems.append('anchor_missing_forbidden')
        if '当前状态' not in anchor_text:
            problems.append('anchor_missing_status')
    log_path = root / 'docs' / 'REVIEW_LOG.md'
    if not log_path.is_file():
        problems.append('missing_review_log')
    else:
        log_text = log_path.read_text(encoding='utf-8')
        log_rows = [line for line in log_text.splitlines() if re.match(r'^\|\s*\d+\s*\|', line.strip())]
        if len(log_rows) < 5:
            problems.append('review_log_too_short')
        for line in log_rows:
            cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
            if len(cells) < 5:
                problems.append('review_row_malformed')
                continue
            if not re.match(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$', cells[1]):
                problems.append('review_row_date:' + cells[0])
            if not cells[3]:
                problems.append('review_row_verdict:' + cells[0])
        if '共因' not in log_text:
            problems.append('review_log_missing_common_cause')
    freeze_path = root / 'docs' / 'STAGE_FREEZE.md'
    if not freeze_path.is_file():
        problems.append('missing_freeze_doc')
    else:
        freeze_text = freeze_path.read_text(encoding='utf-8')
        for heading in ('## 已证明', '## 未证明', '## 禁止的结论'):
            if heading not in freeze_text:
                problems.append('freeze_section_missing:' + heading.strip('# '))
        if 'EXTERNAL_ANCHORS.md' not in freeze_text:
            problems.append('freeze_without_anchor_reference')
        if 'I1' not in freeze_text:
            problems.append('freeze_without_ceiling')
    problems.extend(scan_docs(root))
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