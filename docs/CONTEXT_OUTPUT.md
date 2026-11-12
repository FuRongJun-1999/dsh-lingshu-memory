# 可信Context、快照与输出提交点

状态：proposal。[纯谓词](<../framework/security.py>)、[独立预期](<../tests/test_security.py>)、[行为变异](<../tests/test_security_mutations.py>)不提供认证器、签名、网络服务或原子发送。既有[API草案](<API_DRAFT.md>)的输入安全约束保持不变。

## 两种形状不能混同

API Context还携带auth_method与request_id用于认证归因/追踪。这里context_shape验证的是输出安全子集：tenant、principal、clearance(0..3)、auth_epoch、policy_generation、expires_at；后面三个整数严格0..2^53-1（布尔不是整数），身份字符串1..128字符。闭集拒绝额外字段；业务payload不得构造此可信子集。

形状合法不代表身份真实。tenant/principal来自真实认证会话；auth_epoch由入口维护，撤销会话、角色/组或凭证变化使epoch失效；clearance变更即使epoch漏更新也因绑定比较拒绝。policy_generation代表完整当前策略代际而非可见边子集。expires_at与now来自可信时间设施；时钟回拨/重启无法确定期限时拒绝输出，不能用调用方now延长授权。

## 绑定不可变输出而非重盖章

输出绑定包含完整可信安全子集、snapshot(id/content_generation/policy_generation/expires_at)、read_kind、query_sha、response_sha及cursor_sha。snapshot策略必须与Context一致；digest为小写SHA256。cursor_sha明确null（无输入cursor）或实际输入cursor原始字节摘要，只允许search/expand携带；query_sha覆盖全部语义参数，含排序/limit/来源开关，不覆盖易变追踪信息；具体编码由适配器协议固定，未实现前不得接生产。

response_sha覆盖实际即将发送的完整不可变响应字节，不只是正文；禁止包括被过滤目标的IDs/计数/引用。prepared记录生成时真实代际；current须用同一实际响应/页对象重新获取当前身份/策略/快照与digest，不能把旧结果元数据重新盖成新代际来绕过检查。

emit_allowed只在：当前authenticated/allowed/cursor_validated均严格true，所有绑定逐项相等，now严格早于Context与snapshot的到期点时成立。allowed必须检查实际输出的每项内容、来源标识、回执、聚合和覆盖计数；查回执的权限不意味着正文可读。get/receipt或无cursor时cursor_validated=true的可信证明只能表示确实没有分页输入，不代表跳过输出授权。

## cursor协议与旧提案关系

既有cursor_valid仅覆盖旧草案字段，是必要但不足条件。新输出规格还要求实际cursor绑定auth_epoch/clearance/read_kind/tenant/principal/query_sha/内容快照/策略代际/期限，与当前真实页一致；适配器完成所有校验才可给cursor_validated=true。缺少新字段的旧cursor拒绝并重新从头查询，不自动补值。模型不解析或签名cursor，可信布尔是证据占位，不是可让客户端声称的开关。

## 原子性与分页生命周期

1. 先认证、冻结查询和完整策略/内容快照；候选在排序/截断/扩展前过滤。快照缺失/过期/代际不明阻断，不拼接两个代际的索引结果。
2. 构造不可变输出与binding；输出提交点再次检查上述谓词。
3. 实际运行时必须将代际复核、响应对象固定和发送/队列接收线性化放同一输出租约或等价原子边界。仅调用谓词再socket.send仍有TOCTOU，当前NOT_RUN。
4. 撤权后拒旧binding/cursor/cache，重查当前快照；不得重用旧页再盖新章。续页快照可保持内容不变但不延续旧权限。快照回收或时钟不确定立即失效，不静默转到新快照续旧cursor。

无法撤回已经合法发送给对方的字节；不声称零时序/资源侧信道。流式输出每块独立重复边界检查，未定义真实协议前禁用流式正文。核心冻结规则未改，此提案没有把Context dict升级成可信认证。
