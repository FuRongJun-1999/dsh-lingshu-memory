# 原子提交与取消协议提案

状态proposal；没有实际WAL、锁、CAS或平台I/O实现。纯模型不证明真实并发。

## 提交域与线性化点

K=(tenant, authenticated principal, original operation, caller token)。提交和取消必须在同一协调域CAS并带fencing epoch；取消不分配新token逃离原请求。同节点不同K修改也必须资源revision CAS。

| 状态 | 动作 | 目标与前提 |
|---|---|---|
| 未占位 | accept | 在线完整受理历史同epoch内原子占位K+fingerprint为pending |
| pending | commit | CAS epoch/状态/expected revision/策略代际，原子发布新revision、唯一active、token终结 |
| 未占位/pending | cancel | 同域CAS封存cancelled并fence旧worker；可靠持久确认后才absent |
| committed | cancel/repeat | 当前授权后返原提交，不能变absent或隐式撤销正文 |
| cancelled/rejected | repeat | 同指纹返原终结，不释放K；不同指纹冲突 |
| unknown/残缺/冲突 | write/cancel | 隔离查询同token，不凭空盘面猜测absent |

sealed_cancel是同token域CAS后已持久、且能fence旧worker的证明，不是取消请求已发送。commit/cancel最多一方最终生效，或unknown；cancel赢后延迟worker发布必须失败。取消不撤销过去已经提交的内容。

## 否定证据分型与旧提案修正

此前retry_action仅看absent，可能把已取消token误判首次应用；现改默认unassessed只查询。

- fresh_unseen：只在在线、可信完整受理历史、同一epoch、无任何封存终结且同一临界区授予首次应用资格；不能缓存跨重启使用。不是从磁盘全无推导的恢复状态。
- preaccept_rejected：本K封存拒绝，返原拒绝，不可再写。
- durable_cancel：本K封存取消，返原取消，不可再写。
- unassessed：证据不完整/不匹配/多个类别冲突，只查询。无记录不构成fresh。

恢复模块原规则不变：重启全无unknown；只有权威受理前拒绝或可靠持久取消且无冲突才能恢复absent。process档M2任意子集丢失，不能证明取消封存或fresh的跨epoch有效性；缺可靠证明就unknown。

## 发布与审计

未来先受控恢复payload+intent，再准备revision；commit record/token终结/投影发布必须由选定事务后端保障一个原子边界。文件rename不能单独证明多文件事务。新revision严格递增，唯一active的切换不能暴露双active中间态。
正文恢复日志与payload-free审计权限/保留期分开。commit已知后audit失败只回显audit/error，不回退absent，不重复写正文。strict/power未有平台实证则拒绝，不能静默降级。
当前回执授权先于历史回放；回执权限不代表当前正文权限。撤权与输出发送须在输出提交点重新核对策略代际。

## 运行时实验（全部NOT_RUN）

1. 同K同指纹跨进程竞争只一份commit；不同指纹最多一方成功；同节点不同K同revision只有一方成功。
2. commit/cancel双向交错：commit赢不得absent；cancel赢挡住旧worker；丢证据则unknown。
3. 逐点kill：占位前后、intent后、revision写中、发布前后、token终结、审计失败、回复发送前后。
4. 取消seal首次目录创建/轮转、短写/满盘/fsync失败、M2任意子集丢失、foreign tenant证据。
5. 策略收紧与响应发送竞争：旧cursor/receipt授权不可跨代际重放。

每项固定commit与合成数据摘要、调度轨迹、注入FAIL和撤销PASS、退出码及独立复核。后端尚未选型，未执行任何生产迁移。
