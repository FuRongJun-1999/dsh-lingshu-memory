# 公开方案基线交付验收单

## 交付边界

本基线完成对象是“公开1.0框架的可持续维护方案”，不是生产Memory1.0软件发布。承接[章程](<CHARTER.md>)；M4细化、M5影子运行时及M6真实迁移不因本次交付自动完成。不存在可直连生产的API、认证器、存储后端或升级工具。

## 原目标逐项证据

| 要求 | 固定产物与可复验依据 | 结论边界 |
|---|---|---|
| 公开独立仓库 | [仓库](https://github.com/FuRongJun-1999/dsh-lingshu-memory)、[MIT](<../LICENSE>)、[入口](<../README.md>)、[贡献规则](<../CONTRIBUTING.md>) | 非旧仓原地升级 |
| rev12独立审查起点 | [原包摘要与两次固定来源](<SOURCES.md>)、[五项ADR](<adr/0001-baseline.md>) | 五项逐项处置，不沿用旧自检保证 |
| 可追溯架构 | [L3-L0职责](<ARCHITECTURE.md>)、[规格权威ADR](<adr/0002-spec-authority.md>) | L0是架构职责，不是已选后端 |
| 结构化契约 | [完整核心真源](<../spec/core.json>)、[冻结锁](<../spec/contract.lock.json>)、[生成文档](<CONTRACTS.generated.md>) | 核心0.1.0，完整摘要0b73148ae2bddf3a94dd544aa6f9f0387ed43091e298e9c67fe337a2ae986740 |
| 四应用提案 | [11输入变体](<API_DRAFT.md>)、[schema](<../spec/api.schema.json>)、[响应提案](<RESPONSES.md>) | 不是可调用API；所有旧action不在此封闭面 |
| 参考模型与反例 | [核心](<../tests/test_model.py>)、[API](<../tests/test_api.py>)、[响应](<../tests/test_responses.py>)、[迁移](<../tests/test_migration.py>)、[输出保留](<../tests/test_security.py>) | 手工独立预期，不从模型输出生成 |
| 变异能红 | [核心7](<../tests/test_mutations.py>)、[API7](<../tests/test_api_mutations.py>)、[响应6及终结重用1](<../tests/test_response_mutations.py>)、[迁移7](<../tests/test_migration_mutations.py>)、[安全9](<../tests/test_security_mutations.py>) | 37行为变异，另有3规范变异；不计成37次生产故障实测 |
| 安全设计 | [权限血缘](<SECURITY_MODEL.md>)、[Context输出](<CONTEXT_OUTPUT.md>)、[保留规划](<RETENTION.md>) | 未实现真实认证、原子输出、法律合规删除 |
| 恢复设计 | [恢复三态](<RECOVERY.md>)、[事务边界](<TRANSACTIONS.md>)、[取消响应](<RESPONSES.md>) | 空盘unknown、process M2任意子集；严格持久化NOT_RUN |
| 迁移与验收设计 | [迁移阶段](<MIGRATION.md>)、[固定44个顶层候选](<COMPATIBILITY.md>)、[条件时间](<CONDITIONS_TIME.md>)、[验收矩阵](<ACCEPTANCE.md>) | action/字段转换未全覆盖；禁止生产迁移 |
| 蜂巢复核与修正 | [核心裁决](<adr/0001-baseline.md>)、[API](<reviews/API-proposal.md>)、[响应](<reviews/response-proposal.md>)、[迁移](<reviews/migration-proposal.md>)、[安全保留](<reviews/context-retention.md>) | 独立规则反例已落地；全文代码终审空轮不计成功 |
| 本地/公开CI | [总门禁](<../scripts/check_all.py>)、[CI工作流](<../.github/workflows/spec.yml>)、[运维协议](<OPERATIONS.md>) | 本地101项测试；最终须固定本文件所在SHA并收取4矩阵结果 |

## 公开历史证据与最终判据

- [首批84c1b75](https://github.com/FuRongJun-1999/dsh-lingshu-memory/commit/84c1b7528ccef2bf3b76c59b702381060a328810)：[四矩阵运行43139529041](https://github.com/FuRongJun-1999/dsh-lingshu-memory/actions/runs/43139529041)。
- [输入提案373f27c](https://github.com/FuRongJun-1999/dsh-lingshu-memory/commit/373f27c82de27e34914be57aa0deb65a0283a83d)：[运行43144977904](https://github.com/FuRongJun-1999/dsh-lingshu-memory/actions/runs/43144977904)。
- [响应提案4c4c1f2](https://github.com/FuRongJun-1999/dsh-lingshu-memory/commit/4c4c1f2bd29d883f22b92970a4e79839e51a13de)：[运行43147240939](https://github.com/FuRongJun-1999/dsh-lingshu-memory/actions/runs/43147240939)。
- [兼容提案0d9b4f7](https://github.com/FuRongJun-1999/dsh-lingshu-memory/commit/0d9b4f7bfbe1476602e5e0909d87bef74c11c01f)：[运行43149296137](https://github.com/FuRongJun-1999/dsh-lingshu-memory/actions/runs/43149296137)。

历史绿不证明当前树绿。为避免自引用commit摘要循环，本文件不填自己的SHA；发布回执必须报告本文件实际所在commit、对应Actions run URL、Windows/Ubuntu × Python3.11/3.13四项success、本地远端一致且干净。缺任一项不判最终交付完成。该门禁可从公开commit和Actions日志复验，不需私有日志或记忆库。

## 独立审查范围裁决

整体范围独立复核要求最终SHA重新绑定CI，以及代码终审失败不得偷换成审查通过，均采纳。多次全文/小面代码终审因空助手轮失败，没有成功代码审计报告。维护者在既有全权设计授权内接受以下**方案基线范围**替代：成功的规则级独立复核、公开逐项裁决、独立固定预期和37行为变异+3规范变异，配合最终四矩阵CI；不声称外部全文代码认证，更不解除任何运行时门禁。

接受该范围不是用户接受生产风险，也不代表测试能穷尽正确性。未来运行时发布前必须重新做可成功取证的代码/安装包审查与故障验证，不能引用此次替代裁决绕过。

## 未完成项及重新开启条件

[R01-R09](<ACCEPTANCE.md>)保持全部NOT_RUN。[后续路线](<ROADMAP.md>)包括完整records输出与错误面、真实Context建立、旧action/参数转换、条件语言与时间精度转换、策略/索引原子快照、事务后端与平台故障、物理擦除/法律保留、网络适配器和性能资源预算。

上述每项必须以新的明确范围、反例和发布门禁验收；不在本任务中自动扩大生产授权。若最终CI失败、核心锁漂移、高风险反例未解或误含私有信息，本基线验收保持未完成并先修正。
