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

若模型用布尔量表达否定证据，只是在假定其权威性；不是已实现的不可伪造证明。

## 持久化档位

process仅承诺M1进程崩溃后committed正文可读。M2掉电可任意子集丢失，不承诺持久前缀，不把“禁止中间空洞”的测试当物理保证。
strict/power须平台实证才能启用：正文文件与发布目录先持久，审计文件及首次创建/轮转目录后持久。平台未支持/未验证目录持久化则拒绝power，不静默降级仍宣称power。
审计失败必须回显；正文成功不代表审计成功。strict不产生S3的定理只针对相应add revision、模型内故障，不包括合法forget或保留期清理后的历史不可读。

未来可用durable intent/WAL，但正文恢复日志与payload-free审计职责、保密、保留期、恢复权威必须分开。
没有恢复日志不得声称可从全无盘面重建正文。

真实SIGKILL、断电/VM强停、短写、磁盘满、目录首次创建/轮转、并发和响应丢失实验现在均NOT_RUN。
