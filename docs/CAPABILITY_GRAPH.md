# 记忆能力图与迁移判据

[结构化功能图](<../spec/capability_graph.json>)登记依赖、阶段、可调用入口和验收位置。[行数与依赖检查](<../scripts/capability_graph.py>)对「隔离实测」节点统计登记的手写实现：专属模块、适配函数及当前分派函数的完整物理行均计入，同一行只计一次；测试、规格、文档和具名单列的共享能力不计入。上限 500 行，不得把专属逻辑挪到未登记文件。共享节点也单列实际模块与符号并受 500 行门禁；它们的行数与依赖者分别报，不把传递依赖叠加成单项核心。机检覆盖登记范围，审查仍须核对是否漏列依赖和专属逻辑。

~~~mermaid
graph LR
  G[按标识授权回读] --> A[共享授权判据]
  G --> T[共享条件与时间判据]
  G --> S[快照与正文端口]
  Q[可授权候选检索] --> A
  Q --> T
  Q --> S
  Q -. 候选不等于正文 .-> G
  W[写入受理与幂等裁决] --> X[共享文件事务与恢复]
  R[治理受理与修订变更] --> S
  R --> A
  R --> V[版本绑定核验证明]
  K[授权节点当前核验态] --> V
  K --> A
  E[授权单节点来源出边] --> A
  E --> T
  Z[授权双节点时间关系] --> T
  Z --> A
  L[授权当前修订时间线] --> T
  L --> A
  WN[授权时间窗锚点] --> T
  WN --> A
  TC[授权当前修订时间证据检查] --> T
  TC --> A
  SC[授权单槽状态事件投影] --> A
  SE[授权单槽事件追加] --> SC
  SE --> X
  SL[授权单槽租约视图] --> SE
  EA[授权节点证据审计] --> K
  EA --> E
  RH[授权只读能力建议] --> Q
  HH[按需查询公开能力条件]
  TP[显式任务状态迁移] --> SE
  RF[授权源区间精确回读] --> SR[共享源授权与版本闸门]
  SR --> A
  DS[授权文档章节引用] --> RF
  CD[授权 Python 顶层声明引用] --> RF
  P[独立恢复方向] --> S
  C[任务触发证据取用] --> O[合成授权读取与观察端口]
  C --> G
  C --> Q
~~~

虚线表示计划接线，不表示已迁移或已验收。图中“待迁移”指尚未完成独立接口和逐项旧版对照，不否认已有影子能力。

## 按标识授权回读

- **接口：** [read_get](<../framework/read_get.py>)。可由内存夹具直接调用，也由[影子文件库](<../shadow_runtime/store.py>)在文件锁下调用。文件库负责事务恢复及快照校验，核心不选目录、不接宿主。
- **生效条件：** 调用方提供可信主体、时钟和稳定的读快照；变更时更新代际。仅接受合法 `Read.get`，只按指定时间轴判断。主体上下文不是凭据验证。返回 locator 包含当前修订和摘要；当前输入不支持指定历史修订。
- **子功能：** 判断权限、应用条件与时间、按已选修订读正文、封装出典、发出前复核授权与内容定位。
- **执行：** 无权限与不存在合并为同一结果。确定不匹配返回空；条件未知返回延期；正文与选定版本摘要不符不交付。交付前再次核对主体、时钟、代际、修订和可见性。正文始终为不可信数据。适配器在做快照时可能校验正文哈希；核心不会在拒绝时调用正文交付端口。
- **验证方式：** [独立测试](<../tests/test_read_get.py>)、迁移 S4 对照和 [Docker 接线](<DOCKER_MCP_LAB.md>)。检测回读前越权、输出前撤权、版本漂移、条件未知和正文损坏；各实测结果只对执行该次的字节和环境成立。
- **不适用条件：** 不负责旧版分页、待审提案视图、按文本检索、生产鉴权或网络发送原子性，不读取现有 DSH 库。

[固定上游读取分支](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L3507-L3528)以显式节点标识选按 ID 分支。这里只迁移“按明确标识回读”的能力，保留本仓 v2 规范及权限拒绝语义；不复制旧分支的返回形状、不默认为旧版逐字节兼容。

## 可授权候选检索

- **接口：** [read_search](<../framework/read_search.py>) 使用显式快照、倒排索引、正文读取端口、主体和时钟；[共享排序](<../framework/ranking.py>)不依赖文件库。结果只有候选定位符、下一页提示或错误，不含正文。
- **生效条件：** 倒排索引与快照匹配；只将通过授权、条件及指定时间轴的候选送入 BM25；请求带游标时，偏移由调用方验证。独立接口不会发行游标。
- **执行：** 条件未知阻断，不拿部分候选冒充完整结果。隐藏记录不进入评分、文档频率或截断；授权后的排名材料核对正文摘要。适配层维持原 `Read.search` 输出格式、绑定分页并在发送前复核。拿候选交给 `Read.get` 时须核对返回修订与摘要，不能用旧候选替代当前授权。
- **验证方式：** [候选测试](<../tests/test_read_search.py>)覆盖冻结查询、可见池、排名故障和空结果；[Docker 实测](<DOCKER_MCP_LAB.md>)观察真实工具调用中的授权与未命中。
- **不适用条件：** 不保证计时侧信道、旧版的词法/语义融合、按 token 预算召回、待审核项、标签过滤或开放语义理解。[固定上游源码](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L3542-L3668)包含多种检索路径；本节点只独立实现当前影子库明确、可复验的候选语义。

## 写入受理与幂等裁决

[独立裁决接口](<../framework/write_token.py>)接收已通过 v2 校验的写请求，以及调用者在同一库锁下按 tenant、principal、operation、caller token 取得的账本和 intent 证据。它不查盘、不认证主体、不写回执。

- **生效条件：** 两处证据均确认未见，才返回首次受理候选；这不等于已授权或已提交。只要已有意图且不能证明提交，同指纹保留未知；证据冲突或损坏时不放行。
- **执行：** 同作用域同指纹且提交证据完整时回放原写者回执；异指纹冲突仍拒绝；已持久取消不再写入。回执的审计结果仍由影子库结合实际审计计算。事务文件、锁、清单提交点及恢复顺序未改。
- **验证方式：** [判据与变异](<../tests/test_write_token.py>)、既有跨进程幂等测试，以及 [Docker 强停](<DOCKER_PROCESS_LAB.md>) 和 [MCP 回放](<DOCKER_MCP_LAB.md>)。判据观察包括回执一致、取消不放行、无证据不冒充已提交、审计不重复。
- **不适用条件：** [固定上游写入口](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L3805-L3836) 还支持元数据补丁并调用旧写链；此处不迁移该补丁或审核治理。本节点验证隔离写链，不保证平台掉电或生产认证。

## 治理受理与恢复方向

- **治理接口：** [decide_govern](<../framework/govern.py>)在受信快照下校验主体、版本、状态与策略上限。恢复动作只有在前置条件满足后才查询证明。判定不写库；影子适配负责生成并提交变化。
- **恢复接口：** [decide_recovery](<../framework/recovery_plan.py>)消费持锁、已校验的 intent 和清单。提交前/后只允许匹配一个，矛盾或不匹配均拒绝。方向不是文件完整性证明；改盘前仍须校验元数据与正文。
- **验证方式：** [独立判据](<../tests/test_govern_recovery_plan.py>)、[四动作故障窗口](<../tests/test_shadow_runtime.py>)及[真实强停实验](<DOCKER_PROCESS_LAB.md>)。四动作均使用故障注入；Docker 另实跑 Write.create 和 Govern.forget 各三个真实 SIGKILL 窗口。
- **范围：** [固定上游遗忘入口](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L4001-L4025)供语义对照，不迁移档位、旧审核队列或旧库文件格式。不验证物理掉电或真实生产鉴权。

## 任务触发证据取用

- **接口：** [select_evidence 与 revalidate_evidence](<../framework/context_recall.py>)消费受信搜索与回读端口，不选库；[控制器](<../sandbox_runtime/controller.py>)保留预算、实际动作观测、一次性票据与告警。
- **条件：** 任务已校验并声明所需知识键、架构、版本和条件；先文本定位，允许重取时再确认完整键组；触及键组上限或出现多个匹配不放行。交付前盖住任务和主体变化，重新回读每条证据；不能返回部分正文。
- **验证：** [独立接口测试](<../tests/test_context_recall.py>)核对操作顺序及版本差异；[控制器变异](<../tests/test_controller_mutations.py>)继续检查跳过重读、歧义和版本等故障。[Docker 复验](<../scripts/docker_context_lab.py>)在无网容器的实际 CLI 子进程观察三种结果：正常取用、错版本降级、零调用预算不访问端口。
- **边界：** [文件端口](<../shadow_runtime/recall_port.py>)另接显式合成影子库，文本阶段调用候选接口，正文调用授权回读。同键组扫描先授权，截断即拒绝。取用固定清单且最后复验；不承诺随后网络交付的原子性。正文中的知识键、架构和版本以显式条件属性登记，不从正文猜；预算只计端口次数与回读正文 UTF-8 字节，不覆盖索引和完整性校验读盘。[固定旧入口](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L3559-L3573)供召回输入条件对照，不复制旧版 token 截断、自然语言推断或近况融合。真实宿主、生产与 LLM 效果仍未运行。

## 版本绑定核验证明

[证明构造与适用判据](<../framework/verification.py>)单独接收受信主体与时间证据，生成节点、修订、正文摘要、来源与用途绑定。用途或当前版本不符、来源自证或封签漂移都不得进入恢复；SHA-256 校验不是认证或签名。影子库保留原证明文件形状、当前提交版本检查和锁。仅对应[固定旧核验入口](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L3960-L3964)的一个子能力，不迁移旧裁决、见证凭据或鉴权协议。[回归](<../tests/test_verification_capability.py>)对比原始、改动和还原后的证据，实际重开文件库验证恢复结果。

## 授权节点当前版本核验态

[独立状态查询](<../framework/read_status.py>)接受显式读选择条件、可信主体和当前快照；[文件适配](<../shadow_runtime/status_port.py>)复用事务恢复和锁，不修改证明。权限、条件或时间不满足时不会读取证明端口。只有当前节点、修订、摘要和来源匹配的 full 用途证明才显示 verified；仅用于恢复的证明、未来时间的证明、缺失或损坏的证明均不显示 verified。该状态不是签名或生产身份验证。见[固定旧实现](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L2426-L2447)。不迁移全库巡查、历史台账和冷队列，不暴露证明正文。[定向测试](<../tests/test_read_status.py>)检查拒读、用途和修订切换。

## 授权单节点来源出边

[独立边投影](<../framework/read_edges.py>)接收读选择条件、受信主体和快照；[合成文件端口](<../shadow_runtime/edges_port.py>)使用同一把库锁和事务恢复。根节点不可见与不存在结果相同。仅在根、目标均授权和适用、目标修订与摘要匹配时，投影关系及当前定位符；缺失或不确定的目标不返回，也不报告过滤数量。快照校验可在文件端口内部读取正文摘要，但结果不含正文。若根因版本冲突隔离，则整次拒绝。

对照[固定旧边入口](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L2482-L2507)：此处迁移授权血缘视图子集，不复现按任一端反查、入边、观察轴默认值、时间窗、聚合、展开或寻路。没有新增 MCP 入口。[反例与变异](<../tests/test_read_edges.py>)核验隐边不影响可见输出及目标改版后的拒绝。

## 授权双节点时间关系

[独立时间判据](<../framework/time_relation.py>)对两个当前修订先做权限和条件判定，再比较指定的观察轴或效力轴；[文件端口](<../shadow_runtime/relation_port.py>)在原库锁内恢复并固定两端快照。不可见和不存在都返回同一错误，不标出是哪一端；结果仅含定位符、轴和关系，不交付正文或原段值。未知端点返回 unknown，允许明确的开放边界；零长度返回 empty，相邻端点按左闭右开不重叠。[反例](<../tests/test_time_relation.py>)覆盖端点变异、双轴分歧、目标换版与拒读。

对应[冻结旧入口](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L4953-L4975)与[旧计算](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/stg.py#L493-L506)的时间关系子集。旧版默认观察轴，旧实现相邻区间不判 before/after；新版强制选择轴并有意采用半开语义。空间关系、热层预览、旧协议与生产用户身份均不纳入本批。

## 授权当前修订时间线

[时间线独立接口](<../framework/read_timeline.py>)在显式轴和查询时点筛选已授权、条件适用且可判定的当前修订；[文件适配](<../shadow_runtime/timeline_port.py>)沿用恢复与锁。区间左闭右开；未知端点或无有限起点不进入排序。先过滤，再以起点递减、同起点按标识递增排序并截断。输出只有轴及当前定位符，不返回正文、原区间或计数。[实测](<../tests/test_read_timeline.py>)对比隐藏样例、端点、双轴和修订变化；移除权限判据时反例会变红。

对照[固定旧入口](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L4976-L4982)及[旧时间线](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/stg.py#L602-L660)（源码 SHA256 42ad24f6cbd95244be7406a45c6500e06e44983d89012d7a03a9e55d45c275b9）。本批只做一个查询时点，不复制会话归一、历史路径、跨会话统计、预览、旧协议和生产认证。

## 授权时间窗当前修订锚点

[独立接口](<../framework/time_anchors.py>)在明确选择的轴上与有限非空查询窗比较；[文件端口](<../shadow_runtime/anchors_port.py>)使用同锁已校验的当前修订。先授权及筛选适用条件，再检查时间交集。区间按左闭右开，端点接触不算相交；明确无界不等于未知。只按标识确定顺序、截断至 1–100 项，结果仅含轴及定位符，不含正文、原区间、坐标或全库计数。[定向验证](<../tests/test_time_anchors.py>)涵盖无界、未知、端点变异、隐藏记录与换版。

这是[固定旧 anchors](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/stg.py#L664-L733)的时间窗子集（源码 SHA256 42ad24f6cbd95244be7406a45c6500e06e44983d89012d7a03a9e55d45c275b9），不复刻空间查询、热层、旧缺省轴、索引扫描统计或预览，未接旧协议或现用 GUI。

## 授权当前修订时间证据检查

[独立检查](<../framework/time_consistency.py>)要求显式时点、单轴与条件。可见且条件匹配才判断当前修订；[合成文件适配](<../shadow_runtime/time_check_port.py>)在共享锁内恢复、核对快照。倒置、空区间和已知的区间外时点是冲突；已有确定冲突无需等待另一端点，不能判定时返回 unknown。已知相容只指本时点与该轴，不等于普遍自洽。结果只含定位符和诊断，无正文、原区间、隐藏计数。

[冻结上游检查](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/stg.py#L737-L782)仅作为时间冲突语义来源（SHA256 42ad24f6cbd95244be7406a45c6500e06e44983d89012d7a03a9e55d45c275b9）。不承接全库巡查、空间、旧秒/毫秒归一及默认轴，不补造旧 temporal 字段。[定向与故障变异](<../tests/test_time_consistency.py>)对照半开端点、隐藏与缺失、双轴及换版。未接旧协议或现用 GUI。

## 授权单槽状态事件投影

[独立投影接口](<../framework/state_chain.py>)消费调用方提供的单槽授权、独立链头和事件读取端口。核对主体、槽位、连续序号、前一事件摘要与旧值；与受信链头一致才返回当前值或撤回态。无链头返回未知，空链须有显式零链头。每次最多处理 4096 条，不截取尾部伪造完整结果。拒绝授权时两个读口均不调用；只报告落账时间，不构造第二轴。[反例及变异](<../tests/test_state_chain.py>)覆盖截断、错序、混槽、修改尾部及撤回复活。

[固定上游状态槽位](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/state_slots.py#L265-L288)只读事件而不另存投影（源码 SHA256 3cc173d9d46a41ae5bed0a6a035c741b3bf6908f012a27129a2764db1552be2b）。本批只接合成事件端口；旧台账、追加、MCP 开关、分页与历史不迁。无外部链头分发或签名设施，摘要仅校验输入与受信链头一致，不证明来源身份。影子库修订历史不充当这份台账。

## 授权单槽事件追加

[独立写口及合成文件适配](<../shadow_runtime/state_event_port.py>)要求显式合成库、可信主体和时钟，并在访问盘面前检查单槽写权限。持共享槽锁复核事件链、先前链头与预期旧值；两进程持同链头竞争时只允许一个提交。事件与链头共用单文件原子替换，逻辑只追加；撤回为 null，不迁旧空白串判据。读回用[单槽投影](<../framework/state_chain.py>)。链头来自同一个可信合成存储，不能抗控制存储目录的进程重写，也不是外部链头注册或签名。[反例](<../tests/test_state_event_port.py>)覆盖两进程、过时链头、拒写不触盘、替换前失败和损坏输入。

对照[固定旧入口](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L3929-L3947)和[旧追加](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/state_events.py#L114-L155)（SHA256 ab1211f1479e61498f982b100cc39fa088e851332c7cc69f7471e7ac073c202c）。本批不兼容旧记录、kind/evidence、真实主体令牌、多主机和掉电，不开启 MCP 写口或接现用库。

## 授权单槽租约视图

[独立租约判据](<../framework/state_lease.py>)消费已校验的单槽投影。由受信调用方明确提供正整数 TTL 秒，年龄达到 TTL 即标为 weak，不删除现值。缺失时间证据不伪造稳定；空槽、撤回、未知和损坏分别返回。[合成文件端口](<../shadow_runtime/state_view_port.py>)重用已授权的只读检查，不另存投影或改变台账。[定向反例](<../tests/test_state_lease.py>)覆盖端点、撤回、拒读不触盘和读取不改文件。

此为[固定旧租约](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/state_view.py#L101-L124)子集（源码 SHA256 b444909414d7e8137a8bc6c32085126c88f9e0086a741b939d17f987de309dca）；不迁旧环境变量、槽名缺省、不可变声明、多槽联合或历史输出。时间为受信落账秒，不做真相、签名或生产身份保证；无旧接口接线。

## 授权单节点证据审计

[独立证据接口](<../framework/evidence_audit.py>)额外要求节点审计许可，然后复用可见来源和核验态判据。两个投影必须绑定同一个当前定位符；冲突拒绝，不能交付半份。只返回当前定位符、核验态和至多 64 个可见来源；不返回正文、证明原件或隐边计数。[合成文件适配](<../shadow_runtime/evidence_audit_port.py>)复用库锁及既有事务恢复；查询不改证明或追加审计，先前未完成事务仍按原规则恢复。

对照[冻结五面组装器](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/auditview.py#L136-L248)（SHA256 0fac5a19403229095dba7307bf4f6aaaae9c0792a3401496d03ca88a3b0210b3）；仅迁移当前核验与可见来源子集，不迁旧备择、反向出处、盲区和退役史，也不改事务日志或开放旧 RPC。[定向测试](<../tests/test_evidence_audit.py>)核对审计授权变异、同修订拒绝及重开换版。

## 授权只读能力建议

[独立建议接口](<../framework/route_candidates.py>)只消费无游标的显式检索。候选先经过主体、条件与时间校验，再排序，仅用当前返回页的显式 route.capability 条件属性与宿主白名单求交。结果只有定位符和建议名；不来自正文，不暴露不可见或页外名称，未确认不返回部分建议。建议不是执行许可。[文件适配](<../shadow_runtime/route_port.py>)沿用合成库锁和事务恢复。

对照[固定旧路由](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L3380-L3423)的只读知识定位与能力建议，不复刻热层及全文预览、旧来源标签或全库回退。[定向反例](<../tests/test_route_candidates.py>)覆盖越权、未登记建议、换版和条件未决。不接旧协议、现用 GUI、工具执行或生产数据。

## 按需查询公开能力条件

[独立目录接口](<../framework/capability_help.py>)消费机检后的公开图和可信发布摘要。只在摘要一致时，按能力 ID 精确查找或按 ID 稳定列出至多 64 张隔离卡，输出职责、生效条件、执行边界和依赖名，不出源码入口或底层配置。列表不枚举共享节点，已知共享 ID 和未知 ID 返回相同错误。返回的目录不授予工具权限或生产资格，摘要不是签名。

对照[固定旧披露入口](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L2511-L2520)，只迁按需披露子集，不复制旧版自然语言参数说明及工具表。[定向反例](<../tests/test_capability_help.py>)对比未登记 ID、返回名单限制与摘要漂移变异。

## 显式任务状态迁移

[独立判据](<../framework/task_progress.py>)按已确定的当前状态裁定迁移：空槽只可登记 active，active 可阻塞、完成或放弃，blocked 只可恢复或放弃，done 与 dropped 不重开。完成必须附结果；未知状态不作空槽。[合成端口](<../shadow_runtime/task_progress_port.py>)要求可信调用方授予任务槽的读写权限，核对先前链头；读取至写入之间有并发时，由单槽原子写入口再次对照且失败不返回候选结果。仅合成状态目录，不借任务号读其他槽。

参照[固定旧任务入口](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L2525-L2578)的登记、进度和完成判据；不迁同名合并、跨任务查询、计划、会话装配和经验/记忆归档，不开放旧协议。[定向测试](<../tests/test_task_progress.py>)检查终态变异、未授权、重开合成库和读写间旧头竞争。

## 授权源区间精确回读

[独立接口](<../framework/source_ref.py>)只接已登记源 ID、整源摘要、闭合行号及区间摘要。受信宿主先校验主体对该源的读取权限，再交回不可变 UTF-8 快照。缺失与拒绝同一错误；源换版即使选中行未改也不返回文字。按 LF 分行，保留原 CRLF 及无换行末行；输出标为不可信内容，不作工具指令。没有宿主路径、目录遍历或默认源目录。

参照[固定旧引用入口](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L4796-L4818)的区间回读和漂移检测。只验证合成源端口，不迁旧 path/root、索引巡查、读码工具或清理。摘要不是生产权限或签名。[定向反例](<../tests/test_source_ref.py>)验证权限先于端口、原字节行边界及整源漂移变异。

## 授权文档章节引用

[独立构造器](<../framework/document_sections.py>)只接受已登记、已授权且整源摘要匹配的 UTF-8 快照。只在围栏外识别一级至三级 ATX 标题；跳过开头闭合的元数据块；每段止于下一个受支持标题的前一行。围栏须用同类标记且长度不短于开围栏。标题前普通正文不产生引用。最多 64 段，每段最多 256 行；未闭合或超额整次拒绝。返回层级和字节绑定引用，不返回原文或自动写库。

对照[固定旧标题判据](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/docindex.py#L86-L115)（SHA256 880479af92609ad2ee031d527e7905177731a1e9dfc5525fe3adfb4fb69d5d23），不迁旧目录扫描、小节归并、CCG 渲染、索引写入或水位。[回归](<../tests/test_document_sections.py>)以[源区间读口](<../framework/source_ref.py>)回读每个生成定位符，核对原始字节与围栏变异。

## 授权 Python 顶层声明引用

[独立构造器](<../framework/python_declarations.py>)仅接受已授权、版本一致的 UTF-8 快照。按 Python 3.11 语法口径静态分析，只索引顶层函数、异步函数和类，从 def/class 行开始，不包括前置装饰器。返回名称、类型和原字节定位符，不复制正文，不导入或执行源码；只支持 LF/CRLF，语法错误或超限整次拒绝。

对照[固定旧 Python 抽取器](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/codeindex.py#L140-L180)（SHA256 aad69786d2107b8a852fa4520306862e9945b519f52c5dfb0f4225f8681d2f41）。不迁旧目录扫描、所有语言、嵌套展开、注释渲染、写库或增量水位。[定向测试](<../tests/test_python_declarations.py>)用独立源区间读口核对 CRLF 和末行字节，并验证未授权、语法错误和换版拒绝。

### 三个源接口共享同一闸门

[共享源闸门](<../framework/source_snapshot.py>)统一源授权、整源摘要、字节上限与 UTF-8 检查，回读和两个索引构造器沿用各自区间语义。共享实现单独计量，不以它扩大旧协议覆盖。原授权、版本及区间变异继续运行；[交接说明](<MIGRATION_HANDOFF.md>)列出主线范围及后续复验入口。

## 授权单会话近期事件窗口

[独立窗口接口](<../framework/recent_window.py>)要求可信宿主按明确会话授权、提供同一授权范围内的快照与预期代际；过期或混入其他会话整次拒绝。先校验事件，再按角色筛选、限额并倒序返回。文本标为不可信内容。上限是单次合成快照 256 项，不是全库扫描。

对照[固定旧近期事件入口](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L3890-L3927)，仅做只读隔离子集，不迁追加、清空、自动转录或状态抽取，不连接现用会话。[定向反例](<../tests/test_recent_window.py>)覆盖不触读口、代际变异、混入他会话及先过滤后截断。

## 授权会话续接投影

[独立续接接口](<../framework/session_resume.py>)组合一次授权快照内的近期事件和要点定位符。宿主必须先逐条授权要点；这里核对会话、代际和要点形状，不回读要点正文。共同预算只计事件正文的 UTF-8 字节及定位符字段值，不是序列化字节或模型令牌。显式零预算不读；过代、跨会话和超额均不返回部分内容。

参照[固定旧会话入口](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L4393-L4443)，只做 recall 子集，不生成摘要、不改可见性、不写入或连接真实会话。[反例](<../tests/test_session_resume.py>)检查快照只读取一次、外会话不泄露及零预算不读。

## 授权显式条件依赖路径

[独立路径接口](<../framework/causal_path.py>)只沿宿主在同一快照中登记的精确条件依赖定位符，逐跳核对权限、版本、时间及条件。按层找一条最短可见链，深度至多 8；超出遍历预算返回错误，不报告无路径。它只证明图内登记关系，不是现实因果推断。隐藏或过期节点不得进入路径；不承诺时间和预算侧信道隔离。

参照[冻结旧路径动作](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L1924-L1940)。不把来源边当成因果边，不接旧权重、语义准入、解释或生产接口。[定向反例](<../tests/test_causal_path.py>)覆盖隐藏跳点、旧修订、环、深度与预算。

## 授权当前显式保护标记检查

[独立检查接口](<../framework/protection_check.py>)要求同锁授权快照和权威标记读口，仅报告当前修订的两个显式标记：不可遗忘与不可覆盖。两者不互推；缺标记证据或定位符不符返回未知，不解释成未保护。未授权不触读口。此结果不授予修改或遗忘权限。

对照[冻结旧检查入口](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L1588-L1605)与[旧判据](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/protect.py#L248-L296)。只迁显式标记观察，不迁层级、评分与自我状态豁免、文件与索引对照、保护写入口或真实库。[反例](<../tests/test_protection_check.py>)核对授权顺序、两位独立和换版变异。

## 授权当前目标候选列表

[独立列表接口](<../framework/goal_list.py>)只消费受信同快照下最多 128 个显式候选及其标签。逐项核对权限、时间和适用条件，随后按当前节点 ID、修订与摘要取标签。按明确状态筛选，以整数优先级降序、ID 升序打破平局，再限制条数；只返回定位符、状态与优先级。隐项及旧版不占输出名额，不承诺计时侧信道隔离。

对照[冻结旧列表分支](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L3879-L3885)。不做全库列表、旧活动榜、截止期推导、生成或推进状态，不连 Harness 的自动目标。[反例](<../tests/test_goal_list.py>)覆盖未授权不查标签、稳定限额、空集合仍核对策略和旧修订变异。

## 授权显式派生谱系

[独立谱系读口](<../framework/read_lineage.py>)接收受信宿主在同一快照登记的派生记录，只在两端权限、条件、时间及当前修订均匹配时返回父定位符。按明确关系筛选，去重后按父 ID 排序再截断。超出候选预算不返回半页；不从普通来源边推导谱系，也不保证计时侧信道隔离。

参照[冻结旧派生查询分支](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L3210-L3220)。仅查询当前派生关系，不接握手、对端信任、证据交换、签名、巡检、重建或生产台账。[定向反例](<../tests/test_read_lineage.py>)覆盖隐藏父项、无显式绑定、两端换版和预算。

## 授权条件补充历史

[独立历史接口](<../framework/condition_history.py>)在当前节点可见且适用后，才读取宿主已单独授权并绑定当前定位符的条件补充记录。最多检查 128 条，按修订严格递增校验，非空历史须到当前修订；倒序返回最近至多 32 条。此检查不证明中间修订完整，也不把旧投影当作空历史。文字是不可信资料，不作指令。

参照[冻结旧演化历史](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L1963-L1992)，不迁旧账本、写入、回滚、聚合或生产权限。[反例](<../tests/test_condition_history.py>)验证拒绝时不读历史、过时摘要、重复修订和越界。

## 授权裁决记录元数据

[独立记录读口](<../framework/review_records.py>)要求单提案权限及可信宿主单独提供的完整投影摘要。只接至多 128 条严格递增的记录；仅有裁决类型、序号和修订。即使改变的是最终页以外的记录，也会摘要不符而整次拒绝；成功后倒序返回至多 32 条。这不是签章，也不验证裁决者身份。

参照[冻结旧审核记录分支](https://github.com/FuRongJun-1999/dsh-memory/blob/71efd6785b373a99504b74c61b2c03136d7fd809/md_cg/mcp_server.py#L3966-L3991)，不迁旧账本、摘要编码、待审队列、写裁决或生产接线。[反例](<../tests/test_review_records.py>)覆盖无权不读、他提案或擅带正文、预算和页外变化。
