# 上下文与记忆主动取用闭环

状态：C0契约及C1/C2隔离实现。用户确认同仓、DSH先行、隔离可运行闭环；不改研究或现用生产。旧[基线](<BASELINE_ACCEPTANCE.md>)与核心冻结不变。

## 断点与来源

理论输入为用户提供的上下文管理v7及工具边界。候选不等于出处、表述在场不等于遵守、日志缺失不证明动作未发生、结构代理不等于LLM准确率。未核实研究文档公开性和许可，本仓不搬研究原文或实验数字。

固定[上游源码](https://github.com/FuRongJun-1999/dsh-memory/tree/f251ad86425e2ece7f338c11c9e3c10c15a2ba2c)：md_cg/context_plan.py、constraint_watch.py、context_audit.py、constraint_audit.py、version_anchor.py及src/hooks.ts。context_audit第109-129行说明候选回取不改上下文；constraint_watch第132-164行需核对候选；hooks第940-945行有assemble入口。源码盘点不冒充运行实测，自动注入不等于任务适用检索。

## 架构闭环

L3接任务、续接、assemble、decision事件；L2实际编排检索、原文回读、条件版本核验、拼装、有限重取与输出gate；L1保持授权、完整血缘和策略版本；L0显式隔离合成库及locator。任务和session不是认证。无隔离能力必须失败，禁止默认生产回落。DSH事件重放不冒称现用GUI接线。

任务ID/修订/对象/版本/条件/预算→检索→授权候选→locator(id/revision/hash)精确字节回读→条件版本核验→拼装→输出检查。切换任务及压缩恢复重建绑定。可追溯不证明语义蕴含，语义审定来源明确，未知保留unknown。失败实际有限重取，仍不足则报警或无事实输出；降级不夹带旧事实、越权ID或未核验片段。

事件来自实际调用边界；独立桩计数、字节、库快照和效应探针与日志对账，不接受agent正文自报。未接入gate的输出不在控制范围。

## 反例与验收

蜂巢三项反例采纳：无关dummy search骗通行、degraded标签夹带旧事实、fake分支生产回落及日志丢失。核实际引用链、降级内容与真实效应，不查标签就放行。

[计划](<../spec/context_loop.json>)和[规划检查](<../tests/test_context_contract.py>)不证明运行时。C0契约；C1隔离存储；C2真实动作环；C3 DSH事件重放/重复错序/恢复；C4独立行为负例、变异和噪音规模基准；C5当前SHA四矩阵CI与整体验收。

固定合成语料、种子、正确locator、噪音级和预算，分报主动取用、定位、引用gate、真实动作与LLM效果。不得编造可信提升百分比，零命中不证明不存在。最终须可运行CLI/重放和失败注入，文档或纯谓词绿不能关闭目标。当前C1存储及[C2动作环](<CONTEXT_ACTION_LOOP.md>)已隔离执行，[C3归一化事件重放](<CONTEXT_REPLAY.md>)已隔离执行；C4-C5 pending，整体验收runtime及LLM评测NOT_RUN。
