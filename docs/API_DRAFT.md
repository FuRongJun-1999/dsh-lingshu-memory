# 四应用契约字段草案

状态：proposal，尚未纳入核心结构化规格与冻结锁；不是已可调用的API。已有[输入schema](<../spec/api.schema.json>)、[纯验证器](<../framework/api.py>)与[独立反例](<../tests/test_api.py>)，约束和缺口见[ADR-0004](<adr/0004-api-proposal.md>)。输出envelope未实现。

## 可信上下文与调用方数据

可信入口提供 Context(tenant_id, principal_id, clearance, policy_generation, auth_method, request_id)。业务payload不能覆盖这些字段；session_id仅定位，不授予身份。
网络层拒绝未知字段、重复键、非法类型、过大嵌套、超限内容；限制值须另行固定，当前未声称已实现。
控制面与内容面分离：不在正文内嵌系统指令来获取Govern能力。

共享返回 Envelope(request_id, outcome, result, error, evidence_refs)。outcome=ok/error/unknown，三值不等同历史提交committed/absent/unknown。
unknown表示请求结果不确定，必须提供可安全查询的caller token与恢复范围；绝不建议盲目换token重试。
error含code、retryable、details_public；内部stacktrace/源路径/不可见目标标识不对外返回。

## Write

输入：caller_token、operation(create/modify)、expected_revision、content、declared_sensitivity、reader_ceiling、source_edges、condition_space、source_attribution、durability_request。
caller_token作用域来自可信Context；指纹覆盖operation及全部语义字段，canonical规则见[ADR](<adr/0003-request-fingerprint.md>)。
modify必须精确匹配expected_revision；冲突不自动合并。reader_ceiling不能超过主体被授权授予的集合。
输出：historical_receipt(commit_status, token_scope_ref, fingerprint, node_id, revision, content_sha, durability_actual, audit_state)、projection_state。
历史receipt不可随forget被重写；投影与当前读取权限独立获取。

## Read

输入：schema使用kind=Read.get/search/expand/receipt；get用node_id，search用query，expand用node_id与depth，分页有limit、可选cursor、include_provenance。receipt用operation与caller_token，作用域来自可信入口。
输出：snapshot_ref、policy_generation、records、next_cursor、coverage与不可见来源的无标识占位。
候选在排序、limit、分页、图扩展前过滤。不能让总命中数暴露不可见节点数量。
cursor绑定主体/tenant/查询摘要/内容快照/策略代际；重放到另一主体拒绝，权限代际变化必须重新授权或失效，不能用旧快照延续旧权限。
是否可对不可见node_id区分不存在由统一策略确定；默认统一NOT_FOUND_OR_DENIED。

## Govern

输入：caller_token、action(forget/restore/correct_revision/change_policy)、node_id、expected_revision、reason、action_payload。
输出：govern_receipt、new_revision或policy_generation、projection_state、安全影响摘要。
全部action显式授权并审计。correct_revision不得隐式降密/扩权，首版declassification未实现须拒绝；restore不能恢复已失效核验凭证或过期权限。
forget是治理事件，不自动承诺物理擦除所有备份/审计；保留期与删除权利另立协议后才能声称合规删除。

## SelfCheck

输入：check_ids、scope、snapshot_ref，可选authorized_fault_fixture（隔离测试库专用，不能对生产直接注入）。
输出：checks[{id,status(PASS/FAIL/NOT_RUN),basis,evidence,applicability,limits}]与aggregate。
必需项NOT_RUN阻止发布；不适用需列条件且不得豁免其它门禁。未知的check_id不能静默忽略。

## 错误草案

| code | retryable | 公开细节 |
|---|---|---|
| INVALID_ARGUMENT | 否 | 字段/类型，不回显秘密值 |
| AUTH_REQUIRED / NOT_FOUND_OR_DENIED | 否 | 不暴露另一tenant存在性 |
| REVISION_CONFLICT | 否 | 仅已授权资源的当前revision |
| TOKEN_PAYLOAD_CONFLICT | 否 | 调用方自己的token，原正文不回显 |
| RECOVERY_UNCERTAIN | 条件性 | 同token查询，不换token重写 |
| POWER_UNSUPPORTED | 否 | 平台能力缺口，不静默降级 |
| SNAPSHOT_EXPIRED / POLICY_CHANGED | 是 | 新建读快照，不沿用旧授权 |
| INTEGRITY_FAILURE | 否 | 隔离与安全恢复引用，不暴露原始内部日志 |
| RESOURCE_EXHAUSTED | 条件性 | 限额与退避，不保证未提交 |

输入大小和形状已固定在提案schema；conditions暂为文本数组，不解释语义。仍待输出envelope、取消/超时权威判定、条件语言与双时间类型、真实事务和平台持久化。
