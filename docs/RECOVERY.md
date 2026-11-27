# 写入、幂等与恢复

## 三种状态必须拆分

历史提交（token是否提交过）、当前投影（active/tombstoned/superseded/quarantined）和当前授权是三个问题。
forget不抹掉历史receipt，不释放token；modify追加版本而非把旧commit改成没发生。回执查询要按主体作用域鉴权。

## 幂等

唯一键=tenant+authenticated principal+operation+caller token。请求指纹覆盖完整语义字段：内容、安全、来源版本、会话等，而非只正文。
同键同指纹返回原历史回执；不同指纹硬失败。历史残缺无法确认时unknown并阻止同token新写，不能宣称exactly-once。
未来实现须把查重/占位/提交放在同一跨进程临界区；顺序参考模型不证明并发正确。

## 恢复判定

| 证据 | 历史结果 | 限定 |
|---|---|---|
| 匹配正文revision完整存在 | committed | 审计缺失回显missing |
| 正文无、匹配add有 | unknown | payload-free审计不能恢复正文 |
| 恢复后两者全无 | unknown | 扫描无记录不证明从未提交 |
| 明确受理前拒绝或同指纹持久取消且无矛盾证据 | absent | 证据限于本token/请求/受理边界 |
| token、摘要、正文、审计互相冲突 | unknown + integrity failure | 隔离，不补造成功 |

若模型用布尔量表达否定证据，只是在假定其权威性；不是已实现的不可伪造证明。封存拒绝/持久取消返回原终结，不释放同token；在线首次受理资格不等于恢复absent。详见[事务协议](<TRANSACTIONS.md>)和[响应元数据](<RESPONSES.md>)。

## 持久化档位

process仅承诺M1进程崩溃后committed正文可读。M2掉电可任意子集丢失，不承诺持久前缀，不把“禁止中间空洞”的测试当物理保证。
strict/power须平台实证才能启用：正文文件与发布目录先持久，审计文件及首次创建/轮转目录后持久。平台未支持/未验证目录持久化则拒绝power，不静默降级仍宣称power。
审计失败必须回显；正文成功不代表审计成功。strict不产生S3的定理只针对相应add revision、模型内故障，不包括合法forget或保留期清理后的历史不可读。

## Shadow process-crash transaction journal

当前 shadow_runtime 为合成后端实现 token-scoped schema-v2 intent；它不是 TRANSACTIONS.md 的生产CAS/WAL实现。

- intent 和 pending token 先落盘；随后写 immutable MD/meta；有效的 manifest 原子替换是该 shadow 事务的提交判定。单文件 os.replace 不等于多文件原子提交。
- 进程重启后，在处理新请求/回执/索引重建/记录核验前扫描 schema-v2 intent。manifest仍匹配提交前摘要：将已写sidecar恢复到before image，删除可校验且未发布的新revision文件，intent标记aborted；原token保持unknown，绝不转为absent或释放同token。回滚要在第一次改盘前核对 token、所有 sidecar 与正文；证据矛盾时保持盘面。记录核验只对 manifest 当前登记的已提交修订出具证明，也允许核验已遗忘的当前修订以申请恢复。
- manifest匹配after image：校验已提交MD/meta，重建JSON派生index，使用原writer/timestamp幂等补齐payload-free audit行，最终化token回执并完成intent。
- manifest既非before也非after，或intent/meta/hash与真源冲突：fail closed为完整性错误，不猜测或补造成功。缺失manifest但仍有truth文件也拒绝重建。
- 崩溃测试使用fault_hook抛出进程级异常并创建新store实例；不是真实SIGKILL、VM强停、目录fsync、短写或掉电试验。Govern档目前durable=False；不提升M2/M3或power保证。
- schema-v1历史intent不被自动转换；新scanner只恢复schema-v2。既有payload-free audit键集仍可验证，新追加行含稳定token-scope SHA-256 transaction_id，链可混合两种行格式；此digest是可关联的假名标识，不替代秘密token或认证。旧token若无法与projection证明一致仍按旧恢复判定unknown。


没有恢复日志不得声称可从全无盘面重建正文。

另有[Docker Linux 实验](<DOCKER_PROCESS_LAB.md>)在限定的 Write.create 窗口发送真实 SIGKILL，并由新进程通过同一 tmpfs 恢复。它不是断电、VM 强停、短写、磁盘满、目录首次创建或轮转的实证，也不能替代其他环境的独立复验。
