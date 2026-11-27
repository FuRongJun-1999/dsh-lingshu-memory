# 固定上游记忆功能迁移对照（生成）

范围：固定上游提交的 39 个 cg 和 5 个 stg 顶层操作。未运行旧仓，不覆盖 action、参数组合和历史别名。
统计：17 项子集有隔离证据，27 项未迁移，旧接口可调用 0 项。

“子集有证据”只指新版中文功能图中的隔离能力；不表示旧协议兼容。既有 S3 映射保留原冻结基线。
新版节点见[记忆能力图](<CAPABILITY_GRAPH.md>)；旧候选见[兼容候选](<COMPATIBILITY.md>)。

| 上游入口 | 状态 | 条件与新版能力 | 未覆盖 |
|---|---|---|---|
| [cg.route](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L33-L46) | 子集隔离验证 | route.candidates：当前页授权候选的显式能力声明与宿主白名单交集，只建议不执行。 | 不迁旧热层、正文预览、能力标签推断、自然语言与旧工具协议。 |
| [cg.read](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L47-L78) | 子集隔离验证 | read.get：显式节点标识；按当前修订、授权、条件与时间读回。；read.search：显式查询；只在已授权且适用的候选中排序。；context.recall：结构化任务与受信端口；按明确知识键确认并实时复核。 | 未接旧式分页、标签/角色视图、token 截断、近况融合及查询推导。 |
| [cg.write](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L79-L99) | 子集隔离验证 | write.token：显式新建或修改、可信身份及同锁 token/intent 证据。 | 未接旧 upsert、元数据补丁、写入档位或审核队列。 |
| [cg.verify](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L100-L118) | 子集隔离验证 | verify.proof：受信来源、当前已提交修订与摘要；证明仅在规定用途内适用。 | 仅新版隔离证明；无旧 verdict、override、凭据签发或协议适配。 |
| [cg.review](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L119-L151) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.protect](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L152-L170) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.identity](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L171-L202) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.consistency](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L203-L221) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.metacognition](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L222-L241) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.self_state](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L242-L265) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.evolution](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L266-L298) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.sustain](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L299-L354) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.scrub](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L355-L389) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.predict](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L390-L430) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.causal](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L431-L454) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.forget](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L455-L464) | 子集隔离验证 | govern.recovery：治理须通过主体、预期修订与状态检查；恢复须有有效证明。；recovery.plan：仅新版合成文件事务的恢复方向，不是旧遗忘接口。 | 未接旧档位、强制恢复或覆写、旧文件格式；不做物理删除。 |
| [cg.goal](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L465-L501) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.task](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L502-L559) | 子集隔离验证 | task.progress：显式任务 ID、可信读写授权及匹配链头；终态不可重开，完成需结果。 | 不迁旧同名归并、列表、计划、会话装配、记忆归档或旧工具协议。 |
| [cg.recent](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L560-L590) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.state_view](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L591-L604) | 子集隔离验证 | state.lease：可信调用方按槽授权，显式 TTL 秒及同一时钟；到期保留值并标记需复核。 | 不迁多槽组合、旧 TTL 优先级、不可变声明、替代历史或旧工具协议。 |
| [cg.state_event](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L605-L618) | 子集隔离验证 | state.event：可信主体有写槽权限，且持锁比对先前链头与旧值。合成库单文件只追加。 | 不迁旧 JSONL、开放工具面、生产主体令牌、kind/evidence 或旧撤回兼容。 |
| [cg.info](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L619-L628) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.index_code](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L629-L647) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.index_doc](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L648-L657) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.ref](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L658-L676) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.whitebox](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L677-L729) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.theory](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L730-L744) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.link](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L745-L806) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.session](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L807-L833) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.ingest](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L834-L849) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.export](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L850-L871) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.maintain](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L872-L922) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.consolidate](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L923-L941) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.insight](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L942-L984) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.ccg](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L985-L1002) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.status](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L1003-L1015) | 子集隔离验证 | status.current：已授权且条件、时间适用的当前修订；只检查 full 证明。 | 未迁移旧巡查、验证态台账、履历、冷队列或旧状态字段。 |
| [cg.edges](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L1016-L1031) | 子集隔离验证 | edges.visible：按单节点查看已授权且适用的当前来源出边。 | 未迁移旧反查、入边、时间窗、批次、分页与聚合；不返回隐边计数。 |
| [cg.audit](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L1032-L1041) | 子集隔离验证 | audit.evidence：另授审计权限，授权只读快照中组合当前核验态与可见来源。 | 不迁旧五面全部字段、备择、反向出处、盲区和退役史，不替代事务日志。 |
| [cg.help](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L1042-L1051) | 子集隔离验证 | help.conditions：显式图摘要与受信公开图一致，按能力 ID 查条件。 | 不迁旧参数语义搜索、工具面枚举和别名；目录非执行许可。 |
| [stg.relation](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L4953-L4975) | 子集隔离验证 | stg.time_relation：双端当前修订均可见且条件适用；显式单时间轴，不返回空间。 | 不迁旧空间、热层预览、缺省观察轴或原区间输出；相邻端点语义按新版左闭右开。 |
| [stg.timeline](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L4976-L4982) | 子集隔离验证 | stg.timeline：显式轴和时点；只排序已授权且适用的当前修订。 | 未迁旧会话归一、整库时间线、原区间视图、层级与正文预览。 |
| [stg.anchors](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L4983-L4986) | 子集隔离验证 | stg.anchors：显式轴与有限非空时间窗；只投影授权且适用的相交当前修订。 | 未迁旧坐标适配、空间范围、扫描统计或正文预览。 |
| [stg.consistency](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L4987-L4989) | 子集隔离验证 | stg.time_check：可见且条件适用的当前修订，显式轴和时点；未知与确定冲突分开。 | 未迁旧全库巡查、空间、历史时间单位及旧观察轴内 temporal 与窗口映射。 |
| [stg.state_chain](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L4990-L4999) | 子集隔离验证 | stg.state_chain：单槽有可信授权及独立链头；完整事件流本地投影现值或撤回态。 | 不接旧台账与开关，不迁多槽分页、历史/备选、事件追加或生产链头分发。 |
