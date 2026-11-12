# ADR-0004：可执行API提案不冒充运行时

状态：proposal，核心规格0.1.0及冻结锁不变。

采用独立[输入schema](<../../spec/api.schema.json>)表达四应用输入，JSON Schema draft2020-12的有限子集由标准库验证器执行。顶层为互斥kind变体，全部对象闭合，不接收tenant/principal/clearance等自报身份。新字段必须改schema和独立负例；该提案尚未成为1.0承诺。

输入域：UTF-8合法标量、无重复键、无浮点、整数限正负(2^53-1)、canonical或原始JSON字节均不超过131072、容器深度24、值节点10000。reader集合必须唯一且排序；摘要不做Unicode归一化。

Write.modify用node_id和expected_revision，create禁止这两个字段。source_edges绑定revision/hash；条件暂为未解释的文本数组，尚未支持条件语言或双时间schema。可信入口还须验证资源归属、授予权限、密级、边目标与环；输入形状通过绝不表示写入已授权。

Read新增receipt模式，只能查可信主体自己的tenant/principal/operation/token。分页绑定完整查询（kind/limit/include_provenance/扩展深度均计入，cursor自身除外）、快照、策略代际和到期；谓词不签名、不管理snapshot，完整性由未来可信入口负责。binding必须由可信入口提供当前有效快照与当前策略代际，不得从cursor回抄。当前只在整次请求的授权时点判断，撤权与输出提交原子性尚未实现。

Govern纯谓词要求revision匹配、状态有效、重新授权，禁止原地边撤销。correct只返回旧superseded与新active的目标状态；没有原子事务，不能证明并发至多一个active。未来事务必须CAS当前revision与状态、分配严格递增revision、原子切换唯一active。restore重新核验安全与凭证。policy_safe和proof_fresh是可信证据的占位，不允许从业务请求直接取值。

unknown/历史不完整仅可query；完整历史中的权威absent才具备首次应用资格，仍须授权、CAS和唯一token事务。unknown换新token不能解决原操作不确定，纯谓词不能识别任意新token重复语义。超时和取消均不自动产生absent。

SelfCheck必需项缺失按NOT_RUN，重复/未知id拒绝，任何报告FAIL优先；空required拒绝。不支持用自报不适用跳过门禁。

独立设计复核采纳CAS目标、缺失项、模式绑定与unknown反例；拒绝“任何首次token必须已有回执”的字面建议，否则首次写入永远不能开始。

尚未完成：输出envelope schema、可信Context建立、分页快照生命周期、持久intent/取消协议、真实并发、平台I/O证明。测试PASS仅属于纯规格工具。
