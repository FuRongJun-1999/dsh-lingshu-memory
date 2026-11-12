# C5：隔离闭环整体验收

## 裁定和交付范围

裁定：**ISOLATED_ACCEPTED，仅隔离合成闭环**。用户确认的范围为同仓、DSH先行、隔离可运行，而不是设计only，也不授权迁移生产数据、切换服务或安装现GUI插件。该裁定关闭本轮隔离交付，不声称“AI已可信”或生产可用。

[可执行验收入口](<../scripts/context_acceptance.py>)每次实际执行22个独立子进程和三个真实demo，再与[验收报告](<../spec/context_acceptance.json>)逐值比较；任何源码指纹、检查结果或demo摘要漂移均失败，不自动更新报告。源文件指纹覆盖framework、sandbox_runtime、全部测试与本阶段脚本/规格。报告是本仓检查器实测产物，不是外部认证；哈希证一致性，不证明语义真实。

在仓根执行：

~~~text
python -X utf8 -B scripts/context_acceptance.py
python -X utf8 -B scripts/check_all.py
~~~

11项义务和11项负例均映射唯一真实测试函数，映射在[验收器CHECKS](<../sandbox_runtime/acceptance.py>)，报告保留完整名称/实际testsRun/运行断言数/失败与跳过计数。逐项执行不得skip、空函数、expectedFailure、unexpectedSuccess、只有静态不可达断言；父进程核严格类型、失败和错误计数，不因子进程自报passed而吞错。断言计数防空执行，不证明断言本身语义足够；采用已审阅行为反例及变异补强，不对恶意同进程篡改安全保证。

## 义务—实际行为证据矩阵

| 义务 | 实际核验 |
|---|---|
| task_bound_retrieval | 实际search/get/key确认/emit前get，绑定Task |
| filter_before_limit | 隐藏/跨租户/高敏先剔除再limit，不漏ID/计数 |
| exact_locator_readback | id/revision/hash任一错或无权限统一None |
| query_result_claim_binding | prepare后任务/原文变动阻断；不冒充语义蕴含 |
| conditions_and_version | 错架构/版本/条件或越权不能输出 |
| no_facts_in_degraded_output | 第二需求失败清除第一需求事实，不夹部分记录 |
| bounded_refetch_alert | 不相关首检后实际key回取；有限预算失败真实报警 |
| independent_effect_probe | 实际边界请求/结果摘要与独立Probe核对 |
| missing_logs_unknown | 日志缺失为unknown并阻断，不算没有动作 |
| no_default_production | CLI显式synthetic、闭集JSON拒路径/重复键/超长输入 |
| resume_rebind | compact清票据，再resume重检取证，不复用旧证据 |

11负例另逐条实际执行：不检索、dummy检索、自报报警无效应、500噪音、同hash错revision、迟到旧任务、输出前撤权、失日志/未跟踪效应、跨事件预算耗尽、非隔离参数、新stream可信任务重引导。完整函数/计数见报告checks；不以行数、映射存在或总测试数绿代替运行。

三个真实脚本子进程：context_demo正文/locator/任务hash与5调用顺序一致；replay_demo压缩后重检、9调用/95累计字节、最后duplicate只含状态；context_benchmark固定39case与独立预期、动作摘要和公开报告全部一致。历史transcript不是实时再次投递服务，不把旧ready视为当前仍有效。

## 反伪阳性和独立裁定

[验收负例](<../tests/test_acceptance.py>)拒空/skip/expectedFailure/不可达断言/失败、伪passed和非整数计数、重复映射、源码报告漂移、无动作ready/错locator/重复事件夹事实。[5类验收器变异](<../tests/test_acceptance_mutations.py>)要求原版拒绝同一故障、变异版漏检，未靠前置无关检查“误杀”计成功。总181测试本地PASS；C4的39cases及7评价器变异、C3的11事件变异、C2的12控制器变异、C1的6存储变异继续通过；有限覆盖不证明穷尽。

蜂巢独立规则裁定：范围可作为隔离交付关闭门槛，但要求义务/测试/实跑绑定、demo语义断言、边界不越权三条件，已逐项落实。本裁定非源码审计或独立实测认证；此前C3/C4源码审查空助手轮不计成功。

## 明确保留未执行和限制

- [原始C0规划](<../spec/context_loop.json>)保留design_only/runtime_acceptance=NOT_RUN作为**历史计划文档**，其存在检查不是运行验收；本轮隔离状态仅以C5实际报告为准。核心冻结与旧基线不改。
- gui_integration=NOT_RUN：未向现用DSH注册事件桥接，只有已核对上游的assemble/session-event名；其余任务/压缩/resume为归一化测试协议。
- production=NOT_RUN：没有生产认证、并发撤权原子性、跨进程预算、持久恢复或迁移验收，未读取迁移生产数据。当前GUI和服务未改。
- llm_evaluation=NOT_RUN，open_semantic_retrieval=NOT_EVALUATED：要求/key/Context由可信夹具给出；无key词汇不匹配仍找不到。可追溯不等于原文真实/语义蕴含/防提示注入；本系统返回受控证据，不生成任意LLM答案。
- 静态内存、同步单线程；压缩清引用非物理擦除，预算bytes读后累计非硬token/内存/CPU上限；未知实际工作量保守结算，不支持挂起取消恢复。

下一阶段如要接真实DSH/生产记忆或评估LLM任务效果，应另定授权、数据、认证与验收标准；不得将本轮隔离结论外推。公开CI须核验最终提交的Windows/Ubuntu×Python3.11/3.13日志；本地验收报告不自称能证明远端运行，提交后链接和SHA由交付回执提供。
