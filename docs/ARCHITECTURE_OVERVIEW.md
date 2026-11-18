# 灵枢 Memory 1.0 架构总览（人类可读导读）

> **权威与范围声明**：本文是 [dsh-lingshu-memory](<../README.md>) 的**人类可读导读，不新增规范**。
> 可执行核心规则唯一权威为 [core.json](<../spec/core.json>)（当前 `0.2.0`，受 [contract.lock.json](<../spec/contract.lock.json>) 冻结保护；统一条件空间与双时间轴已按 [ADR-0005](<adr/0005-unified-conditions-bitemporal.md>) 纳入真源）。
> 截至当前阶段，`runtime_released: false`：本仓包含**规范真源、参考模型与隔离合成验证闭环（C0–C5）**，**不是**可投入生产的 1.0 运行时；隔离影子运行时 [shadow_runtime](<../shadow_runtime/store.py>)（纯文本 Markdown 真源 + JSON 索引/WAL/Fencing）已落地并通过 `R01–R09` 隔离故障注入；生产环境真实接入与认证仍未发布（生产门禁 `NOT_RUN`）。

---

## 1. 设计哲学（导读归纳）

基于 [项目章程](<CHARTER.md>)、[理论依据](<SOURCES.md>) 与 [core.json](<../spec/core.json>)，全仓约束可归纳为五条原则（此归类为导读说明，具体规则以真源为准）：

1. **真源不可替代**：不可变原文 `revision` 是唯一内容真源；摘要、索引、缓存均属可删重建的派生投影，不得替代原文。
2. **多维正交解耦**：明确拆分来源归因（`role`/`source_kind`）、适用条件、核验证据、身份认证、历史提交记录与当前可见投影。结构合规不等于事实为真，有历史回执不等于当前仍可读。
3. **默认 Fail-Closed（拒止优先）**：遇状态残缺、条件未知、来源悬空或冲突证据，一律落为 `unknown`、最高敏感度或隔离阻断，绝不为了提高召回率猜测或编造 `absent`。
4. **纠正代替抹除**：已提交版本的血缘边禁止原地 `retract`/`delete`；错误通过追加新纠正版本（`Govern.correct_revision`）处理；`forget` 仅改变当前投影，不抹除历史提交或释放幂等 `token`。
5. **先权鉴过滤，后排序截断**：权限与完整血缘封闭判定必须覆盖完整候选池，之后才能排序、分页、截断或图扩展，防止通过总数或顺序泄露隐藏节点。

---

## 2. 分层架构（L3 → L0）与代码地图

依据 [架构](<ARCHITECTURE.md>)，系统在逻辑上分为四层；当前工程仅实现前两层产物（规范与参考/隔离模型），第三层（生产运行时）尚未建成：

```text
+-----------------------------------------------------------------------+
| L3 Adapters（适配器层）                                               |
| 职责：传输校验、建立可信主体与策略快照、配置解析、宿主事件接线        |
| 禁止：绕过契约直读存储；允许业务 payload 自报身份或权限               |
| 现状：纯输入校验(framework/api.py) + 合成CLI(cli.py/replay_cli.py)    |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
| L2 Application（应用契约层）                                          |
| 职责：Write / Read / Govern / SelfCheck 四契约与上下文主动取用编排    |
| 禁止：猜测未知、静默切换主体、在降级输出中夹带未核验片段              |
| 现状：纯状态谓词(api.py/responses.py) + 隔离控制器(controller.py)     |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
| L1 Governance（治理与安全核心层）                                     |
| 职责：权限交集、敏感度聚合、DAG 无环、血缘版本、核验绑定、审计、保留  |
| 禁止：读取环境变量或可变全局身份；仅凭用户可见子集计算权限            |
| 现状：纯参考模型(model.py/security.py)；无真实持久化审计与临界区      |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
| L0 Storage / Index / Rank（存储、索引与排序层）                       |
| 职责：不可变原文 revision、原子发布、索引与确定性排序                 |
| 禁止：反向 import 上层；对外暴露无权限闸门的原始检索                  |
| 现状：仅纯内存隔离合成库(store.py)；生产持久存储/WAL/锁均未实现       |
+-----------------------------------------------------------------------+
```

仓内目录职责（详见 [工作区索引](<../WORKSPACE_INDEX.md>)）：

| 目录 | 定位 | 代表文件 |
|---|---|---|
| `spec/` | 规格真源、提案 schema 与冻结锁 | [core.json](<../spec/core.json>)、[api.schema.json](<../spec/api.schema.json>)、[response.schema.json](<../spec/response.schema.json>)、[contract.lock.json](<../spec/contract.lock.json>) |
| `framework/` | 纯参考模型与状态谓词（非运行时） | [spec.py](<../framework/spec.py>)、[model.py](<../framework/model.py>)、[api.py](<../framework/api.py>)、[responses.py](<../framework/responses.py>)、[security.py](<../framework/security.py>)、[migration.py](<../framework/migration.py>) |
| `sandbox_runtime/` | 显式隔离合成闭环（C1–C5，不接生产） | [store.py](<../sandbox_runtime/store.py>)、[controller.py](<../sandbox_runtime/controller.py>)、[replay.py](<../sandbox_runtime/replay.py>)、[benchmark.py](<../sandbox_runtime/benchmark.py>)、[acceptance.py](<../sandbox_runtime/acceptance.py>) |
| `scripts/` | 规范生成、索引、合规扫描与总门禁 | [check_all.py](<../scripts/check_all.py>)、[spec_tools.py](<../scripts/spec_tools.py>)、[public_guard.py](<../scripts/public_guard.py>)、[workspace_index.py](<../scripts/workspace_index.py>) |
| `tests/` | 独立手写预期测试与变异杀伤自证 | [test_model.py](<../tests/test_model.py>)、[test_mutations.py](<../tests/test_mutations.py>) 等 |

---

## 3. 四大应用契约（核心概念 + 提案状态）

核心规格 [core.json](<../spec/core.json>) 规定应用契约分为 `Write`、`Read`、`Govern`、`SelfCheck` 四类。
具体请求字段、错误码与响应元数据目前处于 **`proposal`（提案阶段，尚未进入核心冻结锁）**，参见 [四应用字段草案](<API_DRAFT.md>)、[响应元数据提案](<RESPONSES.md>) 与 [ADR-0004](<adr/0004-api-proposal.md>)：

以下表格中“关键约束”为导读归纳，部分约束来自提案文档与验收矩阵（非全部已入核心冻结锁）：

| 契约 | 提案变体（`api.schema.json`） | 关键约束（含提案/验收项） |
|---|---|---|
| `Write` | `Write.create`、`Write.modify` | 携带 `caller_token` 与完整语义请求指纹（整数型 JSON、无浮点、字符串键）；`modify` 须匹配 `expected_revision`；幂等作用域为 `(tenant, principal, operation, token)` |
| `Read` | `Read.get`、`Read.search`、`Read.expand`、`Read.receipt` | 先过滤再排序/截断；`cursor` 绑定主体、查询摘要、内容快照、策略代际与期限；`receipt` 仅按调用方自身作用域查历史回执 |
| `Govern` | `Govern.forget`、`Govern.restore`、`Govern.correct_revision`、`Govern.change_policy` | 禁止原地删边；纠正走新建 revision；首版未实现 `declassification`（禁止降密扩权）；`restore` 须重新验证策略与凭证 |
| `SelfCheck` | `SelfCheck` | 校验 `C01–C10` / `R01–R09`；任一 `FAIL` 即整体 `FAIL`，必需项缺失或未跑即 `NOT_RUN`，禁止以“不适用”跳过门禁 |

---

## 4. 安全、血缘与核验模型

由 [安全与血缘](<SECURITY_MODEL.md>) 与参考模型 [model.py](<../framework/model.py>) 定义（已纳入 `core.json`）：

- **敏感度与读权限**：敏感度分为 `0..3`（`MAX = 3`）；可信入口校验 `clearance >= 有效敏感度` 且 `principal ∈ 有效读者集合`。
- **四类血缘边**：`derived`（派生）、`corroborating`（佐证）、`contradicting`（矛盾）、`unknown`（未知）。
  - 边必须绑定目标的 `node_id`、`revision` 与 `content_sha`。
  - **严格隔离（`quarantined`）**：任意边出现跨租户（`cross_tenant`）、形成环路（全边集必须为 DAG）、目标缺失/已 `tombstoned`（悬空）、或目标 `revision`/`content_sha` 失配 → 节点立即置为 `MAX` 且被隔离拒读。
  - **继承范围**：仅 `derived` 边向上递归聚合 `sensitivity = max(...)` 与 `readers = 交集(...)`（形成时授权上限约束后续放宽，策略收紧即时生效）。
  - **`unknown` 边**：将当前节点敏感度直接置为 `MAX(3)`（若未悬空且无其余违规，则按模型规则标记 `unknown_relation`）。
- **核验独立性与六项绑定**：核验必须绑定 `subject_revision`、`subject_content_sha`、`scope`、`method`、`credential`、`verified_at`；强制 `verifier_id != source_id`（生产者自报不算核验）；正文改变即失验；**明确不宣称事实绝对真实（`truth_assurance: not_claimed`）**。

---

## 5. 状态拆分、恢复语义与持久化档位

依据 [恢复与回执](<RECOVERY.md>)、[事务协议提案](<TRANSACTIONS.md>)（proposal）与 [保留规划](<RETENTION.md>)（proposal）：

1. **三个独立问题不可混同**：
   - **历史提交**（是否提交过：`committed` / `absent` / `unknown`）；
   - **当前投影**（生命周期视图：`active` / `tombstoned` / `superseded` / `quarantined`）；
   - **当前可读性**（当下主体是否有权读正文或查回执）。
   - `forget` 只把投影改为 `tombstoned`，**不会**把历史 `committed` 改写为 `absent`，也**不会**释放已用 `token`。
2. **恢复判定**：
   - 重启后盘面全无 → **`unknown`**（扫描无记录不证明从未提交）。
   - 仅有正文无审计 → `committed`（审计回显 `missing`）；仅有 payload-free 审计无正文 → `unknown`（审计不能恢复正文）；证据冲突 → `unknown` + 完整性失败。
   - 判定 `absent` 必须同时具备“权威受理前拒绝或同域 CAS 持久取消”且无任何冲突证据；在线受理资格 `fresh_unseen` 严禁冒充恢复状态。
3. **持久化档位**：
   - **`process`**：只面向进程级语义，掉电后允许**任意子集丢失（`arbitrary_subset`）**，不承诺持久前缀。
   - **`power`**：要求正文与发布目录先持久化、审计与轮转目录后持久化；**未获目标平台真实目录/文件持久化实证前拒绝启用，禁止静默降级**。

---

## 6. 上下文主动取用隔离闭环（C0–C5）

为在无生产后端条件下验证“Agent 取用上下文不断链、不夹带未核验片段”，仓内构建了 [C0–C5 隔离闭环](<CONTEXT_LOOP.md>)：

- **C0 契约规划**（[context_loop.json](<../spec/context_loop.json>)）：定义 11 项义务与 11 项负例。
- **C1 隔离存储**（[store.py](<../sandbox_runtime/store.py>)）：纯内存合成库，借用 `Model.can_read` 先过滤全图再排序截断，统一 `None` 拒绝。
- **C2 动作环**（[controller.py](<../sandbox_runtime/controller.py>)）：两阶段控制（`prepare` 颁发仅含身份的 `Ticket`，`emit` 单次消费并复核 `task_sha`/实时原文/授权），配合独立 `Probe` 对账与 `AlertSink` 效应核验。
- **C3 归一化事件重放**（[replay.py](<../sandbox_runtime/replay.py>)）：模拟 `task/start`、`system-prompt/assemble`、`context/compact`、`session/resume`、`decision`、`session/close`；`compact` 清票据，`resume` 强制重新检索取证；累计 `calls`/`bytes` 预算不随压缩重置。
- **C4 固定合成基准**（[benchmark.py](<../sandbox_runtime/benchmark.py>)）：39 个固定 case（含 0/10/100/1000 噪音与 15 负例），如实分报文本定位与显式 key 回取结果。
- **C5 隔离验收**（[acceptance.py](<../sandbox_runtime/acceptance.py>)）：子进程逐条执行 22 项测试并校验实际断言计数与源码指纹，当前裁定为 `ISOLATED_ACCEPTED`。

---

## 7. 诚实边界、已知差距与后续路线

1. **现状边界（重要）**：
   - `C0–C5` 的通过仅代表**隔离纯内存合成闭环**逻辑成立，**不代表生产可用、不代表 LLM 效果已评测、也不代表已接入现用宿主插件**。
   - 多文件原子事务、跨进程锁、真实身份认证、条件语言求值、双时间轴整合、完整 `records` 返回体 schema、以及物理删除合规流程均尚未完成。
   - [验收矩阵](<ACCEPTANCE.md>) 中的运行时门禁 `R01–R09` 全部为 `NOT_RUN`。
2. **路线图与存储底座方向（待建设）**：
   - 依据 [长期路线](<ROADMAP.md>)，`M0–M3` 已完成，当前处于 `M4` 设计推进期，`M5`（影子运行时）与 `M6`（授权试点）尚未开始。
   - 后续 M4/M5 存储底座规划坚持**纯文本可读路径**：以 **Markdown 文档作为不可变原文真源 + JSON 作为结构化索引/Intent/审计账本**，不引入 SQLite 等封闭二进制格式；任何平台持久化声称均须通过独立故障注入实证。

---

## 8. 推荐阅读顺序

1. 状态与边界：[README](<../README.md>) → [项目章程](<CHARTER.md>) → [长期路线](<ROADMAP.md>)
2. 核心规则与模型：[core.json](<../spec/core.json>) → [架构](<ARCHITECTURE.md>) → [安全与血缘](<SECURITY_MODEL.md>) → [恢复与回执](<RECOVERY.md>)
3. 提案与迁移：[四应用字段草案](<API_DRAFT.md>) → [响应元数据提案](<RESPONSES.md>) → [事务协议提案](<TRANSACTIONS.md>) → [条件与双时间](<CONDITIONS_TIME.md>) → [兼容矩阵](<COMPATIBILITY.md>) → [迁移计划](<MIGRATION.md>)
4. 隔离闭环与验收：[上下文主动取用](<CONTEXT_LOOP.md>) → [C5隔离验收](<CONTEXT_ACCEPTANCE.md>) → [方案基线验收单](<BASELINE_ACCEPTANCE.md>) → [验收矩阵](<ACCEPTANCE.md>)
