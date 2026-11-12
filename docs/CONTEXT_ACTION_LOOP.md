# C2：隔离主动取用动作环

状态：C2已在内存合成库和真实CLI子进程执行；不是生产集成，也不是完整C0-C5验收。入口[控制器](<../sandbox_runtime/controller.py>)、[CLI](<../sandbox_runtime/cli.py>)，运行演示：

```text
python -X utf8 -B scripts/context_demo.py
```

[演示夹具](<../spec/context_demo.json>)只有公开虚构widget规则；[脚本](<../scripts/context_demo.py>)用argv+UTF8、PYTHONUTF8=1、shell=False真实启动CLI，向stdin传封闭JSON，不查宿主配置、不找生产库。CLI须显式--synthetic，无文件路径参数；输入最多128KiB，重复键/错类型/未知字段阻断。退出0=就绪，3=缺证或门禁阻断，2=输入无效。不是网络服务、生产认证或对恶意同进程代码的沙箱。

## 真正做了什么

1. 可信合成任务指定id/revision/query及requirements(key/architecture/version/conditions)。conditions只支持string键值精确相等；没有模糊解释器。任务文本的语义抽取未实现，key已给不算开放问题理解。
2. Controller自动先文本检索top4并读原文，再按key实际重取完整候选组；组达64即因无法确认完整性而拒绝，多项精确匹配亦拒绝。其他版本/条件不匹配不作为当前证据；缺少条件不等于适用。一次key回取/requirement，最多8要求；不无限重试。
3. Store独立Probe每次完成调用记录request_id、参数及返回摘要、命中/字节；Controller逐call对账，并在下一call核全部既有探针记录。最后回读也核对，不以有search字样作证。异常调用若不能完成留痕仅能unknown/阻断，不伪装完整审计。
4. prepare只交身份票据，内容留在控制器；emit单次消费、重核Task全文hash、当前Context全部字段和不倒退时钟，再精确get重授权及核对字节、条件版本，全部成功才输出原文及locator。任何失败清除部分事实，metadata-only；AlertSink实际接收效果也校验，假报警=>ALERT_UNKNOWN。
5. calls预算含搜索、所有原文读取和emit复核；bytes是累计读取的UTF8正文字节（重复读取也算），不是token预算/内存分配上限：正文读出后计量，超限立即不输出。固定库初始化/索引及最多64候选遍历不在calls中，不能宣称硬CPU/时间上限。

## 证据与覆盖

[22项控制器行为检查](<../tests/test_sandbox_controller.py>)、[3项CLI实际子进程检查](<../tests/test_context_cli.py>)及[12类行为变异](<../tests/test_controller_mutations.py>)。本地总138项PASS；新增行为包含500条词汇重叠噪音、无关首检真实key回取、错版本/条件/架构、撤权/过期/策略变更、预算含输出、错任务/重复票据、缺/伪造/迟丢日志、后台做了却抛错、第二要求缺证无部分事实、假报警阻断。变异捕获不证明穷尽，语义归属来自可信夹具；没有LLM准确率提升数字。

前序多次蜂巢LLM独立反例审查空助手轮失败，不计成功；后续扩大输出预算获得有效规则级反例复核（不是源代码审计或认证，亦未据此推定空轮根因）。三项建议均补独立可执行检查：文本top4之外冲突必须由完整key组阻断、相同正文hash不能掩盖错误revision、最终日志/字节失败前无stdout事实。预算定义按累计正文UTF8字节，不是body+locator总长。22项控制器检查及12类变异验证；仍不作完整目标验收，事件重放和系统基准待做。

## 尚未覆盖

- DSH真实事件接线、事件重放、重复错序、compaction/resume重绑定待C3；当前GUI和生产服务未修改。prepare新任务使旧票据失效，不等于完整恢复机制。
- 静态内存库、同步单线程；最终Context检查到外部传输间的并发撤权原子性、崩溃持久性、认证来源真实性未解决。Context形状不是认证。
- 哈希与locator只能证字节及出处，不证明原文真假、语义蕴含、无提示注入，原文始终是不可信数据而非可执行指令。无LLM调用，亦不宣称输出原文就是正确任务答案。
- 无key自然语言词汇召回、不同语料/规模/预算的系统基准待C4；本轮500噪音的成功依赖显式key回取。

[总体契约](<CONTEXT_LOOP.md>)仍runtime_acceptance=NOT_RUN；生产R门禁NOT_RUN。公开CI须绑定本轮提交，历史C1绿灯不能替代。
