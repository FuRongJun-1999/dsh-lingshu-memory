# 固定上游记忆功能迁移对照（生成）

范围：固定上游提交的 39 个 cg 和 5 个 stg 顶层操作。未运行旧仓，不覆盖 action、参数组合和历史别名。
统计：6 项子集有隔离证据，38 项未迁移，旧接口可调用 0 项。

“子集有证据”只指新版中文功能图中的隔离能力；不表示旧协议兼容。既有 S3 映射保留原冻结基线。
新版节点见[记忆能力图](<CAPABILITY_GRAPH.md>)；旧候选见[兼容候选](<COMPATIBILITY.md>)。

| 上游入口 | 状态 | 条件与新版能力 | 未覆盖 |
|---|---|---|---|
| [cg.route](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L33-L46) | 未迁移 | 无已验收迁移子集 | 无旧路由与路由副作用的迁移验收；不能用候选搜索替代。 |
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
| [cg.task](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L502-L559) | 未迁移 | 无已验收迁移子集 | 取用消费显式任务；未迁移旧任务状态和归档。 |
| [cg.recent](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L560-L590) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.state_view](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L591-L604) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.state_event](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L605-L618) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
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
| [cg.audit](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L1032-L1041) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [cg.help](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/op_table.py#L1042-L1051) | 未迁移 | 无已验收迁移子集 | 未建立旧参数、条件、权限与输出的独立对照，不提供兼容接线。 |
| [stg.relation](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L4953-L4975) | 未迁移 | 无已验收迁移子集 | 未迁移时空关系与观察轴默认行为。 |
| [stg.timeline](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L4976-L4982) | 未迁移 | 无已验收迁移子集 | 未迁移观察轴时间线及会话过滤。 |
| [stg.anchors](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L4983-L4986) | 未迁移 | 无已验收迁移子集 | 未迁移时空锚与坐标过滤。 |
| [stg.consistency](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L4987-L4989) | 未迁移 | 无已验收迁移子集 | 未迁移时空一致性；不以内部安全判据替代。 |
| [stg.state_chain](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L4990-L4999) | 未迁移 | 无已验收迁移子集 | 未迁移受开关保护的状态投影；不伪造效力轴。 |
