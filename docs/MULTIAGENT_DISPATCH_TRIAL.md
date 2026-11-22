# 多智能体派发实测记录

## 范围与基线

- 目标仓 dsh-lingshu-memory：main@275828ba1d3aa18ec0264d09f589ddd8b62f54f6。原型仓 dsh-memory：main@71efd6785b373a99504b74c61b2c03136d7fd809。
- 使用实际 Hive 调度服务，分别派发确定性命令与只读 LLM 子任务；角色覆盖记录/实现、接口盘点、差距审查、验证和独立复核。
- 没有读写生产记忆、密钥、真实用户会话、插件宿主或企业数据。代码实现只作用于 shadow_runtime 的显式 synthetic backend。

## 已完成的真实工作流

| 阶段 | 调度任务与实际结果 | 观测 |
|---|---|---|
| 双仓准备 | 默认分支完整 clone 超时；改成浅克隆后在 58.185 秒完成，固定主线提交并确认干净。已有的旧原型工作树保持不动。 | 确定性命令可被真实提交/poll；大仓获取需有限深度兜底。 |
| 基线门禁 | 目标仓 scripts/check_all.py 退出 0（32.226 秒）；C5 脚本退出 0（3.608 秒）；shadow 套件 11 passed + 15 subtests（21.682 秒）。 | 先建立源码/测试基线，再进行并行分析。 |
| 并行文档盘点 | 并行派发 API、路线差距、源码交叉审查和原型模块地图；有效 LLM 作业耗时约 108–150 秒。 | 独立任务能同时推进；输出不是自动可信制品。 |
| P0发现与实现 | 独立差距审查发现 meta.json 的摘要/副本核对缺失；最终源码审查另发现 SelfCheck 按 C 前缀伪报 PASS。本地主代理核验后分别将损坏状态fail closed、未实现检查改为NOT_RUN/unknown。Hive 确定性 worker 应用源码，验证worker跑定向/变异测试。 | 不同代理的发现被本地源码核验后才进入实现。 |
| P0定向验收 | shadow runtime、变异、v2 contracts、API 四模块合计 43 passed、100 subtests passed；覆盖治理写路径、meta/manifest分歧、SelfCheck C-only伪PASS拒绝、嵌套source_edges摘要往返和新增变异体。 | 证明隔离实现路径和故障样例，不证明生产安全或抗恶意重写。 |

## 调度质量观察

- **有用发现**：独立源码审查指出 meta_sha 缺位、恢复读回需要 manifest 绑定，并发现 SelfCheck 按标识符前缀给 C 项伪造 PASS；多角色从路线、接口和实现面互补。
- **被主代理驳回的误报**：有代理把已存在的 v2 validator/条件接线误报为缺失；主代理以 framework/contracts.py 和 shadow_runtime/store.py 及回归测试复核后不采纳。
- **上下文错路**：多份只读代理报告声明其文件工具只允许访问另一工作树，实际用错源快照或无法核对提交；这些输出被降级为未验证输入，不作为事实。后来使用默认分支浅克隆和本地根代理源码检查固定基线。
- **集成需要单写者校验**：一次多文件替换脚本未正确累计同一文件的替换，定向测试在交付前暴露；改成全锚点预检、按文件累计后原子替换再继续。没有把失败的中间状态当作最终实现。
- **独立审查需绑定最终快照**：在工作树写入前启动的审查结果只能审其上下文旧版本；必须在实现完成后重新派发审查并核对最终 diff。

## 未关闭的审查项

- [test_shadow_runtime.py](../tests/test_shadow_runtime.py) 的崩溃注入只覆盖 intent/token/md/meta 阶段；manifest/index 有 fault hook，但没有本轮故障注入用例。不能据现有结果声称这些崩溃边界可自动前滚。
- _govern_locked 的 forget/restore/change_policy/correct_revision 与 Write 的 intent/WAL 恢复协议不等价；治理写中途崩溃的恢复与整个库可用性仍需单独设计和测试，本轮未扩展此事务面。
- meta 校验目前严格验证键集和无密钥摘要，不对每个metadata值字段做完整类型/值域校验。摘要用于发现未重算损坏，不是认证或抵抗完全控制目录的重写。
- 本轮补齐 correct_revision 旧meta写回的 fault_hook；其他治理崩溃阶段不因此视为已覆盖。

## 结论

本次确实用多个专门代理完成了并行盘点、缺口发现、实现方案和验证/复核，并通过真实任务提交、状态轮询及测试进程运行形成可观察工作流。结果显示 Hive 能承载真实并行任务，但**不会自动解决上下文授权/路径绑定、证据正确性或结果集成**；最终源码审查、固定提交对照和回归测试仍必须由集成者执行。

此实测没有单代理对照组，也没有按质量、成本、总墙钟时间进行预注册测量；因此不推断多智能体比单体更快或更好。本仓 MCP/HTTP/插件尚未实现，未测试其生产接口；M6真实迁移仍未执行。

## 验收状态纪律

本轮 C5 指纹已在独立重跑复现后绑定到当前测试树：22 项隔离检查通过；最终 scripts/check_all.py EXIT 0，245 项全仓测试通过；production 与 gui_integration 仍为 NOT_RUN，release_gate 仍为 BLOCK。此更新只证明当前合成闭环；spec/acceptance.status.json 的生产/断电字段保持 NOT_RUN，candidate=null、evidence_sha=null、release_markers=[]。不得把单元测试、LLM复核或影子运行结果登记成 production PASS。
