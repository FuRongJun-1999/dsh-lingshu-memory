# 隔离存储C1边界

状态：本地可执行内存存储，非完整上下文闭环。模块[store](<../sandbox_runtime/store.py>)不import网络/文件接口，不发现宿主目录，不连接生产服务。显式synthetic=True只是调用契约，不是数据确属合成的密码学证明；任意Python调用者可改私有字段，因此不是对恶意同进程代码的安全沙箱。

字段闭集、严格整数、稳定locator、实际UTF8正文hash与复制隔离；借用冻结核心Model.can_read做完整血缘/权限闭包，先可见性过滤再排名limit。条件/架构/版本保存但C1不解释：C2控制器核验前不能输出成适用结论。get返回同一None表示不可读/不存在/locator不符，不输出隐藏ID或总候选数；不声称零资源侧信道。

独立反例裁决：路径/链接穿越对当前纯内存模块不适用，因为所有body/key/edges只作数据不作路径；未来文件加载器必须单独规范路径/清单/hash并测试，不能照搬本豁免。授权先limit与冻结hash已落实。Probe现仅调用完成记录，缺request_id、异常调用及独立探针对账仍待C2，不称完整行为审计。精确key定位与词汇召回分别标mode，不把已给key命中当开放问题解决。

[八项测试](<../tests/test_sandbox_store.py>)验证实际search/get与字节、500条无关记录精确key、隐藏候选先过滤、derived继承与悬空隔离、locator/越权一致拒绝、显式隔离、输入/返回复制与到期。另[六项行为变异](<../tests/test_sandbox_store_mutations.py>)要求独立测试能红。

与[新任务目标](<CONTEXT_LOOP.md>)的差距：任务控制器/实际有限重取/报警输出/DSH事件重放/恢复/完整噪音及行为基准/LLM效果尚未实现，本地C1通过不能关闭长期目标。旧生产运行时R门禁仍NOT_RUN。
