"""校验条件功能图、依赖环、可调用入口和专属实现行数。"""
import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framework.spec import parse

LIMIT = 500


def require(ok, message):
    if not ok:
        raise ValueError(message)


def source(root, relative):
    path = root / relative
    require(path.resolve().is_relative_to(root.resolve()) and path.is_file(), f'路径不可用：{relative}')
    return path


def span(path, symbol):
    lines = path.read_text(encoding='utf-8').splitlines()
    if symbol is None:
        return set(range(1, len(lines)+1))
    scope = ast.parse('\n'.join(lines))
    for part in symbol.split('.'):
        found = [n for n in scope.body if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == part]
        require(len(found) == 1, f'无法定位实现：{path.name}:{symbol}')
        scope = found[0]
    start = min([scope.lineno, *(n.lineno for n in scope.decorator_list)])
    return set(range(start, scope.end_lineno+1))


def verify(doc, root=ROOT):
    require(doc['version'] == 1, '功能图版本错误')
    rows = doc['capabilities']
    nodes = {n['id']: n for n in rows}
    require(len(nodes) == len(rows), '功能节点重复')
    visited, active = set(), set()
    def visit(key):
        require(key in nodes, '依赖未登记：' + key)
        require(key not in active, '功能依赖成环：' + key)
        if key in visited:
            return
        active.add(key)
        for child in nodes[key]['dependencies']:
            visit(child)
        active.remove(key)
        visited.add(key)
    report = {}
    for key, row in nodes.items():
        visit(key)
        require(row['state'] in ('planned', 'dependency','isolated'), '状态未知')
        if row['state'] != 'isolated':
            continue
        for label in ('conditions','subfunctions','execution','negative','evidence','upstream'):
            require(row.get(label), f'{key} 缺少 {label}')
        entry = row['entry']
        entry_path = source(root, entry['path'])
        require(isinstance(entry['symbol'], str) and '.' not in entry['symbol'], '入口须为独立顶层符号')
        require(any(isinstance(n, ast.FunctionDef) and n.name == entry['symbol']
                    for n in ast.parse(entry_path.read_text(encoding='utf-8')).body), '入口不是可调用函数')
        counted = set()
        for unit in row['implementation']:
            path = source(root, unit['path'])
            counted.update((path.resolve(), i) for i in span(path, unit['symbol']))
        require(all((entry_path.resolve(), i) in counted for i in span(entry_path, entry['symbol'])), '遗漏入口行数')
        require(len(counted) <= LIMIT, f'{key} 超过 {LIMIT} 行：{len(counted)}')
        for path in row['evidence']:
            source(root, path)
        report[key] = len(counted)
    require(report, '无已登记可调用能力')
    return report


if __name__ == '__main__':
    print('CAPABILITY GRAPH: PASS', verify(parse((ROOT/'spec/capability_graph.json').read_text(encoding='utf-8'))))
