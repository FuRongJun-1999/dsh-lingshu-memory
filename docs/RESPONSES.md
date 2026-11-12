# 响应元数据与取消提案0.2

[闭合schema](<../spec/response.schema.json>)与[纯模型](<../framework/responses.py>)只生成元数据响应，不是完整数据返回API；[独立预期](<../tests/test_responses.py>)不从模型输出生成。核心规格与冻结锁不变。

## 五个正交维度

scope=read/mutation/receipt；outcome=ok/error/unknown；target.commit_status=committed/absent/unknown；target.projection表示当前投影；target.audit表示审计可用性。response.error不是历史未提交的证据。

read没有target，不伪造历史commit。receipt查询目标历史，而不是把查询动作算作写；调用方以request_id和原始请求关联结果。此版本不返回正文、节点ID、内容hash或主体信息，不支持从返回元数据恢复正文。

| 证据或权限 | outcome / code | next_action |
|---|---|---|
| 当前回执权限不足 | error / NOT_FOUND_OR_DENIED；target=null | authenticate |
| read失败 | error / READ_FAILED；target=null | retry_read |
| committed+audit ok | ok；历史仍committed | return_original |
| committed+audit missing/failed/unknown | error / AUDIT_INCOMPLETE/AUDIT_FAILED/AUDIT_UNCERTAIN | reconcile_audit |
| unknown/否定证据未评估 | unknown / RECOVERY_UNCERTAIN | query_same_token |
| 证据冲突 | unknown / INTEGRITY_FAILURE | query_same_token |
| absent+持久取消 | error / CANCELLED | return_original_cancel |
| absent+封存拒绝 | error / PREACCEPT_REJECTED | return_original_rejection |
| 在线fresh_unseen | 仅内部受理资格，不可作为历史响应输出 | 拒绝构建此类回执 |

next_action是调用方可执行的下一步，不用retryable布尔混合“查询”“重新写”“重放”。fresh_unseen仅用于内部受理谓词，不属于恢复absent或历史回执；响应构建器拒绝它。首次应用资格仍需同临界区授权/CAS与token唯一性，不可跨epoch缓存。unknown不能换新token来消除原请求不确定性。

## 授权优先与最小披露

receipt_allowed是同tenant/principal/operation/token且当前回执权限检查后的可信结果；content_allowed是单独的当前正文/投影权限结果。两者都不能来自用户自报bool。
先判断receipt权限再回放；拒绝者target永远null，不因真实状态不同而返回不同元数据。只有回执权限无正文权限者projection=unknown。元数据schema校验不验证授权真伪，调用方必须只使用经过当前授权的构建入口，不能把裸validate_envelope当安全过滤器。

## 取消与回执

已发送cancel、网络超时、seal写失败不等于取消成功。sealed_cancel要求[事务协议](<TRANSACTIONS.md>)中的同域fenced CAS和可靠持久证据；committed与cancel seal并存是冲突而非选择一个结果。partial history/unknown不产生absent。

neg_basis修正是输入提案行为变更：原三参retry_action(absent,true,true)现返回query_only；显式fresh_unseen才获得首次应用资格，durable_cancel/preaccept_rejected返原终结。恢复全无仍unknown，不修改核心规则。

未实现：完整响应records/envelope数据、取消网络接口与请求schema、真实认证、持久intent、跨进程锁、物理持久化、策略与输出原子性。对可信布尔证据的顺序推演不证明生产能力。
