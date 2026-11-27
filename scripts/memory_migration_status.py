"""核对旧入口覆盖情况；只生成中文对照，不路由任何调用。"""
import argparse
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framework.migration import load_inventory
from framework.spec import parse

PIN = {"repo":"FuRongJun-1999/dsh-memory","commit":"71efd6785b373a99504b74c61b2c03136d7fd809","sources":{"cg":{"path":"md_cg/op_table.py","sha256":"47e161e68332fbbb99da501a35c4dfe04af0acf61c100c395e6c116ac82f34d7"},"stg":{"path":"md_cg/mcp_server.py","sha256":"fd367661c814c349ba9ce178a24b58e15981b80a9e858b6759569673edd9cc2e"}}}
PARTIAL = {
    ('cg', 'whitebox'): {'whitebox.readback_probe'},
    ('cg', 'maintain'): {'maintain.propagation_preview'},
    ('cg', 'ingest'): {'ingest.event_preview'},
    ('cg', 'sustain'): {'sustain.heartbeat_status'},
    ('cg', 'theory'): {'theory.declaration_check'},
    ('cg', 'info'): {'info.index_observations'},
    ('cg', 'metacognition'): {'metacognition.calibration'},
    ('cg', 'self_state'): {'self_state.card'},
    ('cg', 'identity'): {'identity.profile_refs'},
    ('cg', 'scrub'): {'scrub.verification_age'},
    ('cg', 'export'): {'export.locator_manifest'},
    ('cg', 'consistency'): {'consistency.exact_conditions'},
    ('cg', 'review'): {'review.records'},
    ('cg', 'evolution'): {'evolution.condition_history'},
    ('cg', 'link'): {'link.lineage'},
    ('cg', 'goal'): {'goal.visible_list'},
    ('cg', 'protect'): {'protect.current_flags'},
    ('cg', 'causal'): {'causal.path'},
    ('cg', 'session'): {'session.resume'},
    ('cg', 'recent'): {'recent.window'},
    ('cg', 'index_code'): {'index.python_declarations'},
    ('cg', 'index_doc'): {'index.document_sections'},
    ('cg', 'ref'): {'ref.source'},
    ('cg', 'task'): {'task.progress'},
    ('cg', 'help'): {'help.conditions'},
    ('cg', 'route'): {'route.candidates'},
    ('cg', 'audit'): {'audit.evidence'},
    ('cg', 'state_view'): {'state.lease'},
    ('cg', 'state_event'): {'state.event'},
    ('stg', 'state_chain'): {'stg.state_chain'},
    ('stg', 'consistency'): {'stg.time_check'},
    ('stg', 'anchors'): {'stg.anchors'},
    ('stg', 'timeline'): {'stg.timeline'},
    ('stg', 'relation'): {'stg.time_relation'},
    ('cg', 'edges'): {'edges.visible'},
    ('cg', 'status'): {'status.current'},
    ('cg', 'verify'): {'verify.proof'},
    ('cg', 'read'): {'read.get', 'read.search', 'context.recall'},
    ('cg', 'write'): {'write.token'},
    ('cg', 'forget'): {'govern.recovery', 'recovery.plan'},
}


def require(value, message):
    if not value:
        raise ValueError(message)


def cell(value):
    return isinstance(value, str) and bool(value.strip()) and not any(c in value for c in '|<>\n\r')


def verify(doc, inventory, graph):
    require(set(doc) == {'format','upstream','operations'} and type(doc['format']) is int and doc['format']==1, '清单格式不符')
    require(doc['upstream']==PIN, '上游来源漂移')
    expected = {(item['tool'],item['op']) for item in inventory['operations']}
    nodes = {item['id']: item for item in graph['capabilities']}
    seen = set()
    for item in doc['operations']:
        require(set(item)=={'tool','op','lines','state','runtime_ready','evidence','gap'}, '操作字段不符')
        key = item['tool'], item['op']
        require(key in expected and key not in seen, '操作未知或重复')
        seen.add(key)
        a,b = item['lines']
        lo,hi = (32,1052) if key[0]=='cg' else (4934,5008)
        require(type(a) is int and type(b) is int and lo<=a<=b<=hi,'源码行号不符')
        require(item['runtime_ready'] is False, '隔离进展不能放行旧接口')
        require(cell(item['gap']), '缺明确未覆盖条件')
        targets = PARTIAL.get(key,set())
        require(item['state']==('partial' if targets else 'not_migrated'), '迁移状态与证据不符')
        actual = set()
        for link in item['evidence']:
            require(set(link)=={'capability','condition'} and cell(link['condition']), '缺子能力条件')
            k = link['capability']
            require(k in targets and k not in actual and nodes.get(k,{}).get('state')=='isolated', '不接受同名或未验收目标')
            actual.add(k)
        require(actual==targets, '缺已登记的隔离对子')
    require(seen==expected, '顶层操作漏报')
    return dict(Counter(x['state'] for x in doc['operations']))


def render(doc, stats):
    src=doc['upstream']; repo='https://github.com/'+src['repo']+'/blob/'+src['commit']+'/'
    lines=['# 固定上游记忆功能迁移对照（生成）','',
           '范围：固定上游提交的 39 个 cg 和 5 个 stg 顶层操作。未运行旧仓，不覆盖 action、参数组合和历史别名。',
           f"统计：{stats['partial']} 项子集有隔离证据，{stats['not_migrated']} 项未迁移，旧接口可调用 0 项。",'',
           '“子集有证据”只指新版中文功能图中的隔离能力；不表示旧协议兼容。既有 S3 映射保留原冻结基线。',
           '新版节点见[记忆能力图](<CAPABILITY_GRAPH.md>)；旧候选见[兼容候选](<COMPATIBILITY.md>)。','',
           '| 上游入口 | 状态 | 条件与新版能力 | 未覆盖 |','|---|---|---|---|']
    for x in doc['operations']:
        a,b=x['lines'];url=repo+src['sources'][x['tool']]['path']+f'#L{a}-L{b}'
        e='；'.join(y['capability']+'：'+y['condition'] for y in x['evidence']) or '无已验收迁移子集'
        lines.append(f"| [{x['tool']}.{x['op']}]({url}) | "+('子集隔离验证' if x['state']=='partial' else '未迁移')+f" | {e} | {x['gap']} |")
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true');a=parser.parse_args()
    doc=parse((ROOT/'spec/memory_migration_status.json').read_text(encoding='utf-8'))
    stats=verify(doc, load_inventory(), parse((ROOT/'spec/capability_graph.json').read_text(encoding='utf-8')))
    path=ROOT/'docs/MEMORY_MIGRATION_STATUS.md'; text=render(doc,stats)
    if a.write:
        path.write_text(text,encoding='utf-8',newline='\n')
    else:
        require(path.read_text(encoding='utf-8')==text,'迁移对照文档与真源漂移')
    print('MIGRATION COVERAGE: PASS',stats,'runtime_ready=0')


if __name__=='__main__':
    main()
