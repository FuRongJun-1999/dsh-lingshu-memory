# 双仓功能地图与实现阶段

> 本文固定比较两个不同项目，不代表能力自动迁移，也不表示目标仓库已经发布生产运行时。

## 基线

| 仓库 | 固定基线 | 定位 |
|---|---|---|
| [dsh-memory](https://github.com/FuRongJun-1999/dsh-memory/tree/71efd6785b373a99504b74c61b2c03136d7fd809) | main@71efd6785b373a99504b74c61b2c03136d7fd809，npm @furongjun1999/dsh-memory@0.11.1 | 当前可运行的多组件记忆系统原型；本任务只读对照，不把生产记忆复制到目标仓。 |
| 本仓 dsh-lingshu-memory | main@275828ba1d3aa18ec0264d09f589ddd8b62f54f6 | Memory 1.0 规格、参考谓词、合成验证环和隔离影子存储；README 明示 runtime_released=false，不是生产 MCP/API 服务。 |

原型的 [WORKSPACE_INDEX](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/WORKSPACE_INDEX.md) 内 HEAD 088c1738 是索引生成时快照，不是本文克隆时的仓库提交。目标兼容候选 [COMPATIBILITY.md](COMPATIBILITY.md) 固定于较早原型 b450d2f4，且 runtime_ready=false；必须按本文原型基线重新核对，不能将该表当成已实施映射。

## 原型：dsh-memory

| 子系统 | 职责 | 实际入口/阶段 | 不应混为 |
|---|---|---|---|
| md_cg/ | 长期记忆/认知图、确定性治理与检索 | python -m md_cg.mcp_server；stdio JSON-RPC。默认基元 cg / stg；细粒度工具面受配置控制。 | 不是本仓 framework 的生产后端，也没有目标仓适配器。 |
| src/ + package.json | TypeScript DSH 插件、工具注册、桥接与配置 | npm 插件入口；src/index.ts:apply、LingshuBridge、selectTools。 | 本仓没有对应的 src/、插件包或宿主清单。 |
| rust/ | 只读检索加速与评测工具 | 独立 Rust crate；按其 README 有库/服务/评测多种形态。 | 不是记忆真源；M1 不自动承诺 Rust 后端。 |
| hive/ | 确定性任务执行与 LLM 委托队列 | spec.json -> result.json；spawn/poll/kill/doctor 等 MCP/CLI 面。 | 调度器本身不是记忆存储，也不是 DSH 插件调用协议的替代。 |
| swarm/ | 蜂群/多进程执行、拓扑和信箱机制 | 独立实验与运行时模块。 | README/模块存在不等于本次测得的自治多智能体收益。 |
| compiler/ | 受限语言解析、语义与验证管线 | 独立中文编译器能力。 | 不是 Memory API。 |
| dsh/、codebuddy/、zcode/、codex/、claude/ | 各宿主规则、插件或 MCP 配置 | 按端独立配置、构建与发布。 | 不能由目录名推断新仓已兼容。 |
| docs/、scripts/、test/ | 设计、工程门禁和跨包测试 | 原型自己的版本、构建与依赖链。 | 原型 CI 绿不代表本仓实现完成。 |

## 待实现工程：本仓

| 层 | 当前产物 | 可声称的状态 | 尚不等价于 |
|---|---|---|---|
| spec/ | core.json、v2 请求/完整响应 schema、兼容候选与冻结锁 | 可执行契约/候选映射；按各自锁和门禁验证。 | 网络路由、可信身份或服务部署。 |
| framework/ | 规范解析、v1/v2 验证、条件/双时间求值、模型/权限/响应/迁移纯函数 | reference/pure logic；v2 由 framework/contracts.py 验证。 | 认证器、CAS 后端、可并发生产事务。 |
| sandbox_runtime/ | 合成内存库、控制器、回放、基准和 C0-C5 | 隔离合成闭环；CLI 强制 --synthetic。 | 宿主会话、真实模型或生产记忆。 |
| shadow_runtime/ | MD 原文 + JSON meta/index/WAL/intent、锁、恢复和审计 | synthetic-only 文件后端；本轮补上 meta 摘要/manifest 对账，仍需隔离测试。 | 产品服务、可信本机身份、抵抗本地管理员重写。 |
| scripts/ + tests/ | schema/spec/public/migration/release/workspace 门禁与固定预期、变异测试 | 本地与 CI 的工程质量门。 | 生产接入证据。 |
| 外部适配层 | MCP、HTTP、宿主插件/连接器 | NOT_IMPLEMENTED / NOT_FOUND | 不能把接口提案或 schema 当作可调用服务。 |
| 真实迁移与发布 | M6 | PENDING；需授权数据、备份/回滚和真实验收。 | 不在本次隔离调度实验中。 |

## 差距路线（按当前证据）

| 优先级 | 范围 | 当前证据/动作 |
|---|---|---|
| P0 已处理（仅 synthetic） | meta sidecar 完整性与 SelfCheck 不得伪造 PASS | 当前 metadata 严格键集/无密钥摘要、活动manifest交叉核对；未实现检查保持 NOT_RUN/unknown。隔离测试和C-only专用变异通过；这不授予生产 PASS。 |
| P1 影子事务语义 | Write与Govern的manifest/index崩溃窗口及token/audit最终化 | 已实现schema-v2 token-scoped intent；manifest匹配before则回滚未提交sidecar并保留token unknown，匹配after则校验truth、重建index、幂等补审计和回执。Write 5阶段+Govern四动作提交前/后重启矩阵通过；只覆盖fault_hook模拟的process crash。真实SIGKILL/VM/掉电、跨文件原子性仍未证明。 |
| P2 schema/运维硬化 | meta value dtype、旧meta格式、回执错误分类/重建路径 | 当前meta读取校验键集+摘要，尚未逐字段校验bool/int/list[str]/edge元素类型；缺少meta_sha的旧shadow目录会拒绝，无自动迁移。先设计明确的失败/迁移行为，再实现。 |
| P3 兼容候选复核 | 逐操作比较目标契约与固定原型基线，确定非目标能力的保留/删除 | 当前44项兼容候选来自较早原型b450d2f4，runtime_ready=0；先对照本文固定的71efd678再决定，不做名字级搬运。 |

生产发布不属于“低优先级”差距：真实身份认证、服务进程和MCP/HTTP/宿主连接器、真实持久化/断电验证、授权记忆迁移与回滚仍是M6和production release gates的前置项；当前R01-R09生产登记保持NOT_RUN，release_gate保持BLOCK。

## 迁移决策

1. 将 dsh-memory 的每一个操作按语义、权限、条件时间、错误和幂等证据映射；名字相近不视作等价。
2. 旧兼容候选中的 extension 保持不可调用；新接口必须显式定义 authorization/context 与 error/next-action。
3. “隔离影子能力已实现”与“生产适配器已实现”作为两种独立状态记录。
4. 任何真实记忆、私有会话、凭据或生产数据迁移均需新的明确授权、最小备份和回滚方案；本仓 CI 和合成演示不能替代。
