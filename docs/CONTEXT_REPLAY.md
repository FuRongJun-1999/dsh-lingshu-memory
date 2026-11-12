# C3：归一化事件重放与恢复取证

状态：隔离重放已运行，非现用DSH插件接线。固定[上游](https://github.com/FuRongJun-1999/dsh-memory/blob/f251ad86425e2ece7f338c11c9e3c10c15a2ba2c/src/hooks.ts)字节SHA256=191df254e39b22710d359ad1835eae258584c5adbce7ed73b4dda29ad8e059c5；真实钩子为system-prompt/assemble(942)与session/event(1128)。其余task/start、decision、context/compact、session/resume、session/close是本仓**归一化测试协议**，不是声称宿主同名API存在。尚未注册/安装桥接器，不改当前GUI和生产服务。

## 可运行

在仓根执行：

~~~text
python -X utf8 -B scripts/replay_demo.py
~~~

[演示](<../scripts/replay_demo.py>)启动[实际CLI](<../sandbox_runtime/replay_cli.py>)，读[公开合成夹具](<../spec/replay_demo.json>)后经stdin输入。start→assemble→compact→resume→decision→重复decision，期望started/prepared/compacted/prepared/ready/duplicate；真实9调用、95正文UTF8累计字节，重复不重发body。输入限256KiB及256事件，无路径参数、无默认生产回落；错误退出3，输入无效2。输出是**测试用历史transcript**，不是可把旧records再次发给模型的投递服务；旧就绪结果不会因为后续变化在历史里被抹除，实时接线需只消费当前事件。

## 状态机契约

[实现](<../sandbox_runtime/replay.py>)要求每事件闭集id/seq/stream/session/task_sha/kind/payload。stream和session是归属，不是认证；Context仍来自可信provider。任务摘要必须匹配当前任务全文，包括预算；不允许迟到旧任务decision消费新任务票据。Task修订对每ID单调；切换清证据。初始bootstrap_task来自可信调用者，首个start须与其完全同hash；新进程不加载票据或证据，只用新stream及可信任务重新开始。真实性不由JSON自身证明。

seq连续；同id同完整事件摘要仅metadata-only duplicate，不证明原任务成功；同id改payload、错序、缺号、错stream/session会销毁票据并desync。desync只能用序号高于观测水位、完整且同hash任务的显式resume恢复，重做实际检索。最多256唯一已消费事件，满额拒绝而非自动忘历史。

assemble实际prepare；decision实际单次emit并实时重授权；compact清除票据/work与控制器内部引用，**不是物理内存擦除保证**；resume重新检索读回，不复用旧证据。重复assemble合法但重新做工作、累计扣账；任务calls/bytes预算跨assemble/compact/resume不重置，可信新修订才新预算。调用前记calls；真实返回bytes先计量；后端抛错无法确认工作量则保守耗尽剩余预算，避免重复异常免费执行。同步执行不支持取消/挂起恢复；累计字节是正文读取量非硬内存/token/CPU上限。

## 验证与独立裁决

[20项状态机检查](<../tests/test_replay.py>)、[4项实际子进程检查](<../tests/test_replay_cli.py>)、[11类状态机变异](<../tests/test_replay_mutations.py>)，连同C2的12类、C1的6类及既有核心门禁，总163测试本地PASS。有限反例不证明穷尽。

蜂巢规则级独立复核三项：①metadata-only输入不得冒充完整判重，代码核完整事件摘要并加反例；②后端实际执行后抛错不能漏预算，补保守预算结算及反复assemble测试；③重启不能失去可信修订基线，bootstrap_task hash及新stream正/负例已落实。另自行取证修正旧任务decision缺任务绑定，补task_sha与迟到负例。两文件独立源码审查返回空助手轮，**不计成功**；规则复核不冒充源代码审计。

[C4固定合成基准](<CONTEXT_BENCHMARK.md>)已实测，C5整体证据矩阵仍待做；原文真假/语义抽取/LLM准确率未知。生产并发撤权原子性、真实宿主事件注册/协议映射、掉电持久性、跨进程预算和认证均不在本阶段通过范围。进程重启预算重置不保证跨进程限额，不把同进程单调检查外推为全生命周期回滚防护。整体验收与生产运行时仍NOT_RUN。
