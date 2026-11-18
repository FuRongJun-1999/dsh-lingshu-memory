# ADR-0005：统一条件空间与双时间轴契约（核心规格 0.2.0）

状态：accepted-for-design；运行时存储与真实认证尚未实现，不因本 ADR 宣称运行时完成。

## 背景与问题

在 `0.1.0` 基线中，仓库内存在三套互不兼容的适用条件（`conditions`）表达，且双时间轴（`observed` / `effective`）未进入核心规格与检索控制环：

1. [输入 schema 提案](<../../spec/api.schema.json>) 使用纯文本数组 `list[str]`；
2. [迁移规划模型](<../../framework/migration.py>) 使用三槽声明 `{carrier, method, existence}`；
3. [隔离沙盒](<../../sandbox_runtime/store.py>) 使用扁平键值映射 `dict[str, str]`。

若在演进中把“缺失条件”“`unknown` 状态”与“已声明相等”混为一谈（例如将 `unknown == unknown` 判为匹配，或将缺少键的旧数组归一为无条件满足），将直接违背 `unknown` 不放行与 fail-closed 原则。

## 决策

按 [ADR-0002](<0002-spec-authority.md>) 纪律将 [core.json](<../../spec/core.json>) 从 `0.1.0` 升级并重新锁定至 `0.2.0`，在核心真源中正式纳入 `conditions` 与 `bitemporal` 两节契约：

1. **统一条件空间（`condition_space`）**：
   - 闭合结构包含三项显式槽位 `carrier`、`method`、`existence`（每项为 `{"state": "unknown"}` 或 `{"state": "declared", "text": "..."}`）与结构化键值映射 `attributes`（`dict[str, str]`，键/值非空且受长度与条数上限约束）。
   - **三值判定（`MATCH` / `NO_MATCH` / `DEFER`）**：
     - 任一槽位或所要求属性存在已知不相等 → `NO_MATCH`（矛盾优先）；
     - 否则任一被评估槽位为 `unknown`、或所需属性在记录中缺失 → `DEFER`（**明确禁止 `unknown == unknown` 判为 `MATCH`**，禁止缺失键视为满足）；
     - 仅当所有被评估槽位均为 `declared` 且文本相等、且所有必需属性显式相等时才返回 `MATCH`。
   - **兼容归一化（`normalize_conditions`）**：旧式 `list[str]`（`"k=v"`）或 `dict[str, str]` 归一化时，缺失的三槽一律填为 `{"state": "unknown"}`（绝不伪造 `declared`），重复键或格式冲突硬拒绝。

2. **统一双时间轴（`bitemporal`）**：
   - 显式要求 `observed`（观察/记录轴）与 `effective`（效力轴）同时存在，禁止互相回退（`no_axis_fallback: true`）。
   - 半开区间 `[start, end)`，时间精度严格为 UTC 秒级 `YYYY-MM-DDTHH:MM:SSZ`；边界 `instant` / `unbounded` / `unknown` 严格三分，`unknown` 绝不等同 `unbounded`。
   - 查询必须显式指定时间轴；多轴联合求值遵循 `NO_MATCH > DEFER > MATCH`，`DEFER` 必须阻断产出（`defer_blocks_output: true`）。

## 后果与约束

- 现有 `0.1.0` 核心不变量（`sensitivity`、`formation`、`edges`、`recovery`、`idempotency`、`verification`）保持原语义不变。
- `framework/conditions.py` 提供纯参考求值器与独立变异测试，供后续 API 提案整合与 `sandbox_runtime`、影子运行时共同引用。
- 纯参考求值器不提供真实时钟服务或权限认证；运行时门禁 `R01–R09` 仍为 `NOT_RUN`。
