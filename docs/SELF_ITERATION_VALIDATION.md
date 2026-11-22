# 自指迭代与分阶段封版协议（提案）

状态：proposal（stage-0）。本文定义项目维护流程，不修改 core 契约、不授予生产资格，也不构成形式证明。核心语义规则仍以 [core.json](<../spec/core.json>) 及其冻结锁为准。

## 1. 目的与共因风险

本项目使用多智能体工作流维护自身。同一模型、提示、规则、测试或工具可能同时作用于实现与验证，形成共因错误：工作流顺利完成任务，不等于工作流判断正确，更不等于系统生产可用。

因此每个阶段同时是一次受限的架构实验，必须满足：

- 变更范围绑定明确的基线提交、组件集合与需要保护的不变量；
- 实现者不能单独决定自己的候选晋级；
- 实现者生成的测试、摘要或代理评价，不单独构成独立验证；
- 未运行、无法读回或证据冲突的门禁保持 `NOT_RUN` / `unknown`，不得推断为通过。

## 2. 三条版本轴

三种版本状态互不替代，均需在阶段回执中记录：

| 版本轴 | 表达什么 | 约束 |
|---|---|---|
| 规范版本 | `core.json` 的契约语义 | 当前 `0.2.0`；本协议不升级、不改写。 |
| 工程阶段版本 | 一组可审阅的项目变更 | `stage-N` 绑定 PR 与提交；标签只表示范围冻结。 |
| 证据等级 | 实际通过了哪些对象与环境 | 逐项声明，如 `spec-tools=PASS`、`shadow-process-crash=PASS`、`C5=ISOLATED_ACCEPTED`；不得压缩成无范围的“1.0 通过”。 |

在项目仍为设计/参考/隔离实现期间（`runtime_released: false`），不使用含混的 `1.0.0 stable` 标签。工程阶段可用 `v1.0-stage.N-rc.M` 作候选标识；正式稳定标签须由维护者另行裁定发布语义后创建。任何标签都不改变 `core.json` 版本或 `runtime_released`。

## 3. 候选状态机

```text
planned -> implementing -> candidate-frozen -> independently-verified -> accepted-for-stage
               |                  |                      |                        |
               |                  |                      +-> rejected             +-> revoked
               |                  +-> invalidated        +-> needs-revision
               +-> abandoned      (any state with conflicting/unreadable evidence -> unknown/contested)
```

`unknown/contested` 是并列的不可晋级态：证据冲突、来源不可读或关键回执缺失时进入，等待隔离查询；它与 `invalidated` 不同——`invalidated` 表示“无有效证据”，不作为证伪结论。

### 3.1 转移与写入权

| 转移 | 谁可写 | 前提 |
|---|---|---|
| `planned -> implementing` | 实现者或编排者 | 范围、基线、组件、风险等级、所需独立性级别与退出条件已在实现前登记 |
| `implementing -> candidate-frozen` | 实现者 | 提交冻结包：候选提交、文件清单哈希、依赖摘要、工具/测试版本、环境指纹 |
| `candidate-frozen -> independently-verified` | 验证者，主体 ≠ 实现者 | 第 4 节要求全部满足且原始回执可读 |
| `candidate-frozen -> invalidated` | 任何人 | 命中第 3.2 节任一失效触发，并记录证据 |
| `candidate-frozen -> needs-revision` | 验证者 | 存在反例、漏项或独立性不足 |
| `needs-revision / rejected -> implementing` | 编排者 | 必须建立新 `candidate_id`；旧证据保留，不得覆盖 |
| `planned / implementing -> abandoned` | 编排者 | 记录理由与已产生副作用 |
| `independently-verified -> accepted-for-stage` | 阶段门裁定者，主体 ≠ 实现者 | 第 6 节全部满足 |
| `independently-verified -> rejected` | 验证者或裁定者 | 记录反例或未满足项 |
| `accepted-for-stage -> revoked` | 任何人 | 失效触发命中，或结论所依赖的工具/测试/oracle 后来被判定有缺陷 |

任何状态下，只要关键回执不可读或与另一回执冲突，均可转入 `unknown/contested` 并阻断晋级。

### 3.2 失效触发（可判定集合）

候选冻结时记录以下摘要；任一变化即触发 `invalidated` / `revoked`：

1. 候选文件清单与内容哈希；
2. 直接依赖与规格锁摘要（含 `spec/core.json`、`contract.lock.json`、规格树锁）；
3. 相关工具、测试与 oracle 的版本或内容哈希；
4. 执行环境指纹（操作系统、解释器版本、平台持久化探针结论）。

无关变更不自动作废全部证据，但必须重绑 manifest 摘要并说明“只复验受影响不变量”的理由；无法证明无关时按失效处理。

阶段接受不自动晋级 `M6`、production/power release gate 或真实迁移，也不改变 ROADMAP 里程碑状态行、任何 `Cx` 裁定等级或 `runtime_released`。

## 4. 自指验证隔离

每个阶段至少设置两个时间上分离的验证窗口，并至少覆盖一个组件隔离的判据面。

1. **实现窗口**：实现者完成变更并提交摘要，不作最终验收。
2. **冻结窗口**：记录候选提交、文件清单、依赖、环境、命令、预期与失败处理；冻结后由独立编排者锁定不可变输入。
3. **独立复验窗口**：候选冻结后另起会话或由不同执行主体执行，并**在验证者自身可访问的路径根内独立读取原始回执**；源不可达一律记 `unknown`，不得以注入文本假定原件（参见 [多智能体实测](<MULTIAGENT_DISPATCH_TRIAL.md>) 的路径错认记录）。
4. **跨组件检查**：对被改组件使用另一个组件、手写预期或外部可观察接口作判据。改 shadow 存储时用真实重开实例检查持久投影；改规格生成器时用冻结输入检查产物与反向漂移；改调度编排时用 worker 原始 status/result 而非编排者摘要。
5. **延迟复验**：至少一项关键不变量在后续独立时段针对同一候选摘要复验；候选变化则新建证据，不移植旧 PASS。

同一底模、同一上下文、共享同一实现摘要的多个代理只算多个审查视角，不算独立。**独立性分级是归因，不是认证**——不得用 `I2`/`I3` 的标记冒充“已认证的独立”。

### 4.1 独立性分级与判据

| 级别 | 判据 | 用途 |
|---|---|---|
| `I0 coupled` | 实现者自测或同上下文复看 | 仅调试，不签发 |
| `I1 fresh-context` | 新会话复跑，但主体/工具/判据仍共享 | 低风险内部检查 |
| `I2 independent-operator` | 不同执行主体；验证者先写下盲化预期再执行，并保留自有执行产物 | 一般阶段门 |
| `I3 cross-component` | `I2` 加不同组件或独立 oracle/手写预期；预期值不得由实现者提供 | 关键不变量默认门槛 |
| `I4 delayed-replication` | `I3` 加后续时段对同一候选摘要复验；记录最小间隔，时间戳不得早于实际结果 | 持久化/授权/迁移等高风险主张 |

每条关键结论记录：`candidate_sha`、被测组件、验证者身份/角色、是否与实现者相同、会话标识、验证时间窗、执行环境、原始命令与结果路径、预期来源、依赖输入摘要、盲区与偏离项。

若无法取得不同主体或独立执行，必须标记 `independence=limited`，此时**禁止**用于：production/power 主张、`M6` 迁移、release gate 变更、公开措辞升格，以及任何被列为关键不变量的结论。

## 5. 冻结证据包

候选提供可读 manifest（建议文件名带 `candidate_sha`），至少包含：

- `stage_id`、目标、非目标、基线提交、`candidate_sha`、精确文件与组件清单；
- `required_gates[]`：每个门禁 id、命令、退出码、原始输出路径、所需独立性级别；
- 本阶段要保护的不变量及来源；正例、负例、故障注入与变异的预期结果；变异集须在实现前声明，存活的等价变异体需给出等价性论证；
- 原始命令、工具与 worker 版本、操作系统与解释器版本、起止时间、测试数/子测试数、失败与跳过计数；required 子集不允许 skip，父进程须核计计数，不因子代理自报通过而吞错；
- 独立性账本、覆盖矩阵、未覆盖面、已知共因风险与复验计划；
- `not_claimed[]`（本阶段未声称的结论）与未做项（如无对照组、无成本/时间测量）；
- 规格、文档、公开内容与隐私门禁读数；若刷新源指纹类报告，须证明重新实跑并读回；
- 对应 PR、提交与远端 CI 回执；生产状态文件与 release gate 摘要。

约束：证据目录 **append-only**，旧回执保留、不得就地刷新；manifest 与门禁脚本对状态文件只读，禁止写 `*_status.json`；`stage_evidence_sha` 只覆盖本阶段证据，不冒充全局状态。

证据产物只描述实际观察。日志被截断、工具超时、代理无法读取源文件、远端 CI 未运行或状态读取失败，一律保留为 `unknown` / `NOT_RUN`，不得由总结补齐。

## 6. 阶段门与封版

每个阶段以独立 PR 交付，合并或封版前至少满足：

1. 变更范围与冻结基线可复核，无意外夹带；
2. 针对性回归通过，风险相符的故障/变异测试能杀死对应缺陷变体；
3. 由不同主体完成 `I3` 复验；高风险阶段安排后续时段 `I4` 复验，或保持候选不晋级；
4. 文档、生成产物、索引与规格锁一致，公开内容与隐私扫描无命中；**公开措辞升格（如“隔离”改为“可用”）必须另有 production 级 manifest**，扫描无命中不能替代；
5. PR 的 base/head/CI 实时读回，生产验收登记未被隔离结果改写；
6. 复核者已列出发现及范围限制；阻断项清零，非阻断待办有负责阶段；
7. 任一 required 门禁为 `NOT_RUN` / `unknown` 时不得晋级；阶段结论取所有 required 结论的最小值。

封版只冻结某候选的源码与适用证据，不是自动合并、自动发布或生产授权。若发布阶段标签，标签必须指向已验收的精确提交，并附同一 manifest 摘要。

可执行阶段门已实现为 `scripts/stage_gate.py`：校验 manifest 字段集、claim→gate 级别绑定、required 门禁未运行、原始日志摘要与实际文件一致、隔离范围内出现生产措辞、复核者自签与状态文件被当作证据。用法 `python scripts/stage_gate.py --manifest <stage-manifest.json>`，退出码非零即阻断；该工具只读，不写 acceptance/release 记录。独立样例与变异自证见 `tests/test_stage_gate.py`、`tests/test_stage_gate_mutations.py`。

## 7. 首阶段与后续顺序

本文件即 `stage-0: self-verification protocol` 提案：只定义流程，不更改 `core.json`、release gate 状态或运行时行为。stage-0 自身即使通过 `I3` 复核，也**不提升任何既有证据等级**。独立复核通过并合并后，后续阶段按风险分开选择：P2 metadata 类型与值域硬化；intent/WAL 与平台故障边界实验；阶段门工具化；`M6` 授权迁移前置评审。不同阶段不得把验证工具自身的 PASS 当作它正确的自证。

M0–M5 现状与 M6 门槛仍以[路线图](<ROADMAP.md>)、[章程](<CHARTER.md>)、[恢复规范](<RECOVERY.md>)与[核心规格](<../spec/core.json>)为准。C5 的 `ISOLATED_ACCEPTED` 只覆盖其声明的 `framework`、`sandbox_runtime`、`tests`（含 `tests/test_shadow_runtime*.py`）与 context 指纹及隔离合成流程，不覆盖 `shadow_runtime/` 实现文件；它既不能证明 shadow 实现正确，也不构成 production/power 证据。`spec/acceptance.status.json` 与 release gate 仍是生产资格真源，不由此流程自动改写。

## 8. 不适用与限制

本提案不是共识协议、加密签名、形式证明、独立组织审计或抗恶意管理员篡改。复核者可能共享模型、库、工具或策略而产生共同失误；`I3`/`I4` 只降低并暴露部分共因风险，不能消除风险。涉及凭据、真实个人数据、生产迁移、线上部署或破坏性操作，仍需单独授权与专项门禁。
