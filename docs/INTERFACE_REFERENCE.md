# 两仓代码接口参考

> 状态标签：SPEC = 结构化契约；REFERENCE = 纯函数/模型；SANDBOX = 强制合成输入；SHADOW = 独立隔离文件后端；PRODUCTION = 已验证生产服务。schema 存在不自动提升接口状态。

## dsh-lingshu-memory

### Python

| 符号 | 签名 | 状态与契约 |
|---|---|---|
| framework.contracts.validate_v2_request | validate_v2_request(value: object) -> dict | REFERENCE/SPEC。载入 spec/api_v2.schema.json，检查闭集形状、字节/深度、读者顺序，并对 v2 condition/bitemporal 字段求规范格式；字段错误抛 ValueError。 |
| framework.contracts.validate_full_response | validate_full_response(value: object) -> dict | REFERENCE/SPEC。按 response_full.schema.json 和语义不变量校验响应；不是网络发送器。 |
| framework.contracts.build_untrusted_record | build_untrusted_record(locator: dict, body: str, provenance: dict | None = None) -> dict | 纯封装和摘要检查；输出显式 untrusted_markdown。不认证来源、不证明内容真实。 |
| framework.api.validate_request / parse_request | 见 framework/api.py | v1 提案验证器；不要和 v2 contracts.validate_v2_request 混用。模块声明不实现 transport/authentication/transaction runtime。 |
| framework.conditions | condition_space、normalize_conditions、condition_match、bitemporal_match | 纯条件/双时间求值。三态 MATCH/NO_MATCH/DEFER 不是授权结论。 |
| framework.responses | envelope、read_response、target_response、cancellation | 纯响应/取消谓词；不写持久状态。 |

新的请求在 schema 中以 kind 描述 Write.create/modify、Read.get/search/expand/receipt、Govern.*、Operation.cancel、SelfCheck。响应 schema 存在不表示完整 production records 查询服务已经上线。

### 隔离文件接口

~~~python
ShadowMarkdownStore(
    root_dir: str | pathlib.Path,
    *, synthetic: bool,
    durability_probe_fn=probe_platform_durability,
    lock_timeout_s: float = 5.0,
    writer_handle=None,
)

store.execute(
    request: dict,
    context: dict,
    now: int,
    *,
    request_id: str = "req-1",
    fault_hook=None,
    current_context_provider=None,
    current_now_provider=None,
) -> dict
~~~

- 构造器要求 synthetic is True，否则 EXPLICIT_SYNTHETIC_REQUIRED；context 是结构校验输入，不是身份认证。
- execute 是 Python 进程内调用，不是 MCP/HTTP endpoint。写操作会在文件系统中产生合成数据，写锁/回执/恢复行为仅属 shadow scope。
- recover_token_state 用于查询 token 恢复证据；verify_record 用于隔离核验记录。损坏的 meta 以完整性失败拒绝。
- meta_sha 是无密钥 SHA-256：能发现未同步重算的损坏/副本分歧；本地完全控制目录者能重写数据并重算摘要，不构成防恶意篡改或认证。 已有但不含 meta_sha 的旧shadow目录按完整性失败拒绝；没有隐式迁移或自动修复。
- SelfCheck 接口目前不执行 C/R 检查：所请求项全部返回聚合 NOT_RUN、outcome=unknown、CONDITION_DEFERRED/refresh_snapshot。不会把检查 ID 前缀解释成证据；生产验收登记仍独立维护。

### CLI

~~~text
python -m sandbox_runtime.cli --synthetic < request.json
~~~

输入是单个闭集 JSON envelope（fixture/context/now/task）；输出 JSON；ready -> exit 0、已运行但未 ready -> exit 3、非法输入/异常 -> exit 2，并以统一 INVALID_INPUT 隐去内部细节。CLI 明确拒绝路径/网络/宿主发现；它不是通用记忆 API。

### MCP / HTTP / 插件状态

| 面 | 本仓状态 | 可用性 |
|---|---|---|
| MCP stdio / JSON-RPC server | NOT_IMPLEMENTED | 没有 server/tool registration/handshake endpoint。 |
| HTTP/REST | NOT_FOUND | 没有 listen socket、路由、HTTP status contract 或认证中间件。 |
| DSH/Codex 插件 | NOT_FOUND | 没有宿主 manifest、安装包、connector、生命周期 hook。 |
| Authentication | NOT_IMPLEMENTED | schema context 与 authenticated 谓词不是身份凭证验证器。 |
| Production persistence/migration | NOT_IMPLEMENTED/PENDING | M6 仍需授权真实数据、备份回滚和外部验收。 |

## dsh-memory 原型

固定源：[71efd678 md_cg/mcp_server.py](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py)。原型为 DSH/MCP 主链，不等于目标仓接口：

- stdio JSON-RPC 2.0，源码声明 MCP 2024-11-05；启动 python -m md_cg.mcp_server，从 MDCG_ROOT / MDCG_ACTOR 读取运行配置。
- 默认导出 cg、stg 两个基元；可选 full granular surface。操作与参数权威来自 md_cg/op_table.py，调用时应以运行时 tools/list 和固定提交核对，不复制历史散文计数。
- DSH 插件入口 src/index.ts:apply(ctx, config)；桥接类 src/bridge.ts:LingshuBridge；工具选择 src/tools.ts:selectTools。实际构建入口/依赖以同提交 package.json 为准。
- npm package @furongjun1999/dsh-memory@0.11.1 提供 bin lingshu、lingshu-init、dsh-memory。工具名别名/安全筛选是原型行为，不是本仓兼容承诺。
- 原型内嵌前端不等于外部稳定 HTTP API；本轮不确认 HTTP 兼容性。

## 兼容边界

目标仓 spec/compatibility.json 只是一份旧 cg 39 + stg 5 顶层操作候选；其固定上游为 b450d2f4，runtime_ready=false。尤其 cg(read/route/write/forget)、时间轴默认、严格条件默认、验证/审核权限均需逐操作定义/验证。不得把 44 项候选写成已接入接口。
