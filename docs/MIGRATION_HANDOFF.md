# 隔离记忆迁移交接

## 当前边界

固定上游 `71efd67`：[44 项顶层入口对照](<MEMORY_MIGRATION_STATUS.md>)为唯一覆盖清单。目前 28 项有隔离子集，16 项未迁移，0 项提供旧协议。这里的“隔离”不等于现用宿主、生产认证或 M6 试点通过。

| 已验证主线 | 独立接口和当前适配 | 限制 |
|---|---|---|
| 授权回读 | [按标识读回](<../framework/read_get.py>)与[文件适配](<../shadow_runtime/store.py>) | 不开放历史修订或旧协议 |
| 候选检索 | [授权排序](<../framework/read_search.py>) | 候选不是正文，不代表开放语义 |
| 幂等写入 | [写入裁决](<../framework/write_token.py>) | 证据不明只查询，不放行新写 |
| 治理与恢复 | [治理受理](<../framework/govern.py>)与[恢复方向](<../framework/recovery_plan.py>) | 真实进程强停不等于掉电 |
| 任务主动取用 | [证据选择与复验](<../framework/context_recall.py>)和[合成文件端口](<../shadow_runtime/recall_port.py>) | 未接真实模型循环或现用 GUI |

## 怎么复验

先读取[中文条件图](<CAPABILITY_GRAPH.md>)和[覆盖清单](<MEMORY_MIGRATION_STATUS.md>)。在仓根运行：

~~~text
python -X utf8 -B scripts/check_all.py
python -X utf8 -B scripts/docker_context_lab.py
python -X utf8 -B scripts/docker_process_lab.py
python -X utf8 -B scripts/docker_mcp_lab.py
python -X utf8 -B scripts/docker_mcp_lab.py --with-dsh
~~~

只用合成夹具，不挂载真实库。门禁的 500 行只计算具名登记的专属实现及单列共享实现，不能自动证明没有漏列。公开 CI（如[交接前固定提交](https://github.com/FuRongJun-1999/dsh-lingshu-memory/actions/runs/45995878469)）核对同一 SHA 的规格回归；Docker 强停和两条 MCP 实验另有[进程实测](<DOCKER_PROCESS_LAB.md>)及[MCP 接线](<DOCKER_MCP_LAB.md>)。本地容器回执的候选树需与发布提交核对，不能只用回执的 base 宣称发布版通过。保持 [阶段台账](<STAGE_LEDGER.md>) 的 I1 上限和生产 `NOT_RUN`。

## 后续

按对照表里的未迁移项选择可检验子集。优先做授权、版本与拒绝行为能明确定义的能力；为每项保留旧源锚点、独立反例、中文条件卡与真实容器证据。缺少旧事件真源、真实令牌或生产验收时，不用新版同名功能冒充完成；未经明确确认不接生产数据或现用 GUI。
