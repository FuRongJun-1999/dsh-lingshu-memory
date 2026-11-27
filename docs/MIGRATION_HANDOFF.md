# 隔离记忆迁移交接

固定上游：[71efd67](https://github.com/FuRongJun-1999/dsh-memory/commit/71efd6785b373a99504b74c61b2c03136d7fd809)。[覆盖清单](<MEMORY_MIGRATION_STATUS.md>)中 44 个顶层入口均有隔离验证子集，0 个可按旧协议调用；这不表示所有动作均已迁移。[中文条件图](<CAPABILITY_GRAPH.md>)的 500 行机检覆盖已登记专属实现，共享实现另列，机检不证明没有漏列依赖。

## 五条主线验收矩阵

[复验基线 40afebd](https://github.com/FuRongJun-1999/dsh-lingshu-memory/commit/40afebdae640200d2438afd62b2016eb11ecfd62)的候选树与发布树均为 d8ca7f693e538f943462ba972e427e2ce6c78261，四路 Docker 与本地 497 项回归通过。[同 SHA 公开 CI](https://github.com/FuRongJun-1999/dsh-lingshu-memory/actions/runs/46023300556)另验规格回归，不代替 Docker。

| 主线 | 独立接口与条件 | 定向与隔离实测 | 未覆盖 |
|---|---|---|---|
| 授权回读 | [回读](<../framework/read_get.py>)：可信快照、当前修订、有效权限及适用条件 | [回读反例](<../tests/test_read_get.py#L36-L54>)覆盖时点不符、完整性错误和撤权；两条 MCP 路径覆盖授权回读与拒读 | 历史修订、生产认证与网络交付原子性 |
| 候选检索 | [排序](<../framework/read_search.py>)：授权和适用性过滤在排序前 | [排序反例](<../tests/test_read_search.py#L31-L82>)覆盖越权、摘要不符与冻结排序；两条 MCP 路径的授权、越权和无匹配对照通过 | 全语料、语义检索和旧排名器等价性 |
| 幂等写入 | [裁决](<../framework/write_token.py>)：首写须有明确证据，提交不明不重写 | [裁决反例](<../tests/test_write_token.py#L16-L33>)；两条 MCP 路径回执重放通过、审计一行；三次强停提交前返回 unknown，提交后回放原写者回执 | 跨主机持久化、生产凭据、断电恢复 |
| 治理恢复 | [治理](<../framework/govern.py>)、[恢复方向](<../framework/recovery_plan.py>)：操作授权、版本前置和明确恢复证据 | [恢复反例](<../tests/test_govern_recovery_plan.py#L9-L53>)拒绝宽化与歧义；Govern.forget 三次实际强停，提交前仍可读，提交后拒读，审计行数 1／2／2 | 其他治理动作只有故障注入，没有实际强停证据；不等于断电恢复 |
| 任务主动取用 | [选择与复验](<../framework/context_recall.py>)、[合成端口](<../shadow_runtime/recall_port.py>)：绑定授权、预算、版本与证据 | [取用反例](<../tests/test_context_recall.py#L12>)区分取正文与确认；Docker 正例退出 0，错版 EVIDENCE_GAP 和零预算 BUDGET 均退出 3，零预算端口调用为零 | 无真实模型主动回取闭环；DSH 工具执行链不是模型闭环 |

## 怎么复验

在仓根运行：

~~~text
python -X utf8 -B scripts/check_all.py
python -X utf8 -B scripts/docker_context_lab.py
python -X utf8 -B scripts/docker_process_lab.py
python -X utf8 -B scripts/docker_mcp_lab.py
python -X utf8 -B scripts/docker_mcp_lab.py --with-dsh
~~~

仅用合成夹具；参见[进程实测](<DOCKER_PROCESS_LAB.md>)和[MCP 接线](<DOCKER_MCP_LAB.md>)。判断发布版是否经过验证须核对候选树与发布树，不能只看 Docker 回执的基线字段。[阶段台账](<STAGE_LEDGER.md>)保留 I1 上限，生产验收 NOT_RUN。未覆盖的动作仍按覆盖清单列出的边界理解，不因顶层全有子集而放行。未接生产数据、真实认证、现用 GUI 或旧协议。
