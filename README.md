# dsh-lingshu-memory

灵枢 Memory 1.0：可审计 Agent 记忆的公开架构与可执行契约框架。

> **设计开发中，不是已发布的1.0运行时。** 不提供生产存储/MCP服务或掉电安全承诺。参考模型只验证规格。

## 阅读入口

新长期任务：[上下文主动取用](<docs/CONTEXT_LOOP.md>)、[隔离存储C1](<docs/CONTEXT_STORE.md>)、[C2可运行动作环](<docs/CONTEXT_ACTION_LOOP.md>)、[C3隔离事件重放](<docs/CONTEXT_REPLAY.md>)（未接现用宿主，完整验收未完成）。

- [方案基线验收单](<docs/BASELINE_ACCEPTANCE.md>)
- [项目章程](<docs/CHARTER.md>)、[架构](<docs/ARCHITECTURE.md>)、[理论依据](<docs/SOURCES.md>)
- [安全与血缘](<docs/SECURITY_MODEL.md>)、[恢复与回执](<docs/RECOVERY.md>)
- [Context与输出](<docs/CONTEXT_OUTPUT.md>)、[保留与删除](<docs/RETENTION.md>)
- [结构化规格](<spec/core.json>)、[生成规范](<docs/CONTRACTS.generated.md>)
- [兼容候选清单](<docs/COMPATIBILITY.md>)、[条件与双时间](<docs/CONDITIONS_TIME.md>)
- [迁移计划](<docs/MIGRATION.md>)、[验收矩阵](<docs/ACCEPTANCE.md>)、[长期路线](<docs/ROADMAP.md>)
- [工作区索引](<WORKSPACE_INDEX.md>)、[贡献约定](<CONTRIBUTING.md>)
- [响应与取消](<docs/RESPONSES.md>)、[事务协议提案](<docs/TRANSACTIONS.md>)
- [四应用字段草案](<docs/API_DRAFT.md>)、[输入schema提案](<spec/api.schema.json>)、[开发运维](<docs/OPERATIONS.md>)

## 定位

承接 [dsh-memory](https://github.com/FuRongJun-1999/dsh-memory) 的设计与实践，不是它的原地升级或生产替代。
历史分析基线：2d67f0bf44980e211445e710237af2d1597bfd56。
启动观察上游：b450d2f451ed33891e3f6587d238d1d4f5c9ecb9，不代表永久最新。

不搬迁生产记忆，不复制原始会话、私有路径或执行日志。旧rev12五项问题在[ADR-0001](<docs/adr/0001-baseline.md>)逐项处置。
规范与工具可以通过验证；真实存储、并发、认证、平台持久化和迁移仍须单独验收。**CI绿不等于运行时已完成。**

## 本地验证

Python 3.11+，标准库，无需安装依赖。在仓库根运行：

~~~text
python scripts/check_all.py
~~~

完整规格变动一律使锁失败；更新锁须升版本、说明理由并独立复核。不得修改测试来掩盖语义漂移。

许可证：[MIT](<LICENSE>)。
