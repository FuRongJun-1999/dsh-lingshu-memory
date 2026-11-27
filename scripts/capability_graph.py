"""校验条件功能图、依赖环、可调用入口和专属实现行数。"""
import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framework.spec import parse

LIMIT = 500
FROZEN_COMMIT = '71efd6785b373a99504b74c61b2c03136d7fd809'
FROZEN_SOURCES = {
    'md_cg/ccgc.py': (1074, 'f3659a689f3867335e934582166869d1362723bddc30c19ec7719d7797fd2252'),
    'md_cg/codeindex.py': (532, 'aad69786d2107b8a852fa4520306862e9945b519f52c5dfb0f4225f8681d2f41'),
    'md_cg/consolidate.py': (1794, 'd5725529ba25ab2688985d351933114233c2424405b78c4effb9abb7ce79201a'),
    'md_cg/docindex.py': (497, '880479af92609ad2ee031d527e7905177731a1e9dfc5525fe3adfb4fb69d5d23'),
    'md_cg/insight.py': (541, '1540b0c96e7a56207576af561c23eacc867abf8e927c6c2e045517635d1bf841'),
    'md_cg/mcp_server.py': (6779, 'fd367661c814c349ba9ce178a24b58e15981b80a9e858b6759569673edd9cc2e'),
    'md_cg/metacognition.py': (780, '861ebfa8bea6be6e14bd8a0a0741d5d4a91abc7233ab254b785b06c5ba1398a9'),
    'md_cg/predict.py': (1104, '796f079a918e427fe1aca4da82805db67420bbbe5a005103240b634d56e5b3bf'),
    'md_cg/scrub.py': (1232, '6645d299cb184cbd72c56edd8b87d2381a71154d0340413aa054500d45188200'),
    'md_cg/state_view.py': (181, 'b444909414d7e8137a8bc6c32085126c88f9e0086a741b939d17f987de309dca'),
    'md_cg/stg.py': (822, '42ad24f6cbd95244be7406a45c6500e06e44983d89012d7a03a9e55d45c275b9'),
    'md_cg/theory.py': (277, '3fc0f69ba4d7b605f75190da9b5863973e4287f2feeded4099d6ec4e2ed983af'),
    'md_cg/trust.py': (1114, 'f6d08ac9791fa881f7a1608428d24869d00d4a485ad6b7fca600114054f7018e'),
    'md_cg/whitebox.py': (537, 'aba3123f91d2092a78c7b119ad96842dd5a5b8403346276bbf668beebff4b4ff'),
}


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
        if row['state'] == 'planned':
            continue
        if row['state'] == 'dependency':
            units = row.get('implementation')
            require(units, f'{key} 共享实现未登记')
            counted = {(source(root, unit['path']).resolve(), i) for unit in units
                       for i in span(source(root, unit['path']), unit['symbol'])}
            require(0 < len(counted) <= LIMIT, f'{key} 共享实现超过 {LIMIT} 行或为空：{len(counted)}')
            report[key] = len(counted)
            continue
        for label in ('conditions','subfunctions','execution','negative','evidence','upstream'):
            require(row.get(label), f'{key} 缺少 {label}')
        upstream = row['upstream']
        require(type(upstream) is dict and set(upstream) == {'commit','path','lines'}, f'{key} 上游锚格式不符')
        require(upstream['commit'] == FROZEN_COMMIT and type(upstream['path']) is str
                and upstream['path'] in FROZEN_SOURCES, f'{key} 上游锚未登记')
        lines = upstream['lines']
        require(type(lines) is list and len(lines) == 2 and all(type(i) is int for i in lines)
                and 1 <= lines[0] <= lines[1] <= FROZEN_SOURCES[upstream['path']][0], f'{key} 上游锚行号越界')
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
    require(any(n['state'] == 'isolated' for n in rows), '无已登记可调用能力')
    return report


if __name__ == '__main__':
    print('CAPABILITY GRAPH: PASS', verify(parse((ROOT/'spec/capability_graph.json').read_text(encoding='utf-8'))))
