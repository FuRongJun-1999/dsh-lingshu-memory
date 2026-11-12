# 审计、遗忘与保留规划

状态：proposal。这里[保留资格谓词](<../framework/security.py>)返回retain、eligible_rebuild_discard或eligible_purge，**不删除任何文件、记录、备份或密钥**，不提供合规法律结论。依据[历史与当前拆分](<RECOVERY.md>)，forget不重写历史commit、也不释放token。

## 独立保留域

| 记录域 | 自动资格规则 | 不能混同 |
|---|---|---|
| body / backup | 非active且非quarantined；本域deadline到达；独立清理授权；无hold；commit已终结；token终结已可靠留存；恢复/前提依赖已关闭 | 逻辑forget不是立即抹除；备份单独有期限与销毁证明 |
| index | 授权且确认无hold时可discard重建 | 不作为正文/审计/幂等真源；丢弃索引不代表介质擦除 |
| audit | 以上条件加独立audit_closed=true | payload-free也可能含敏感标识/摘要，不可公开；不能用正文期限删除审计 |
| token_final | 首版始终retain | 可以最小化正文，但不能删除K/指纹/终结裁决使旧token重新被受理 |
| intent | 非active/非隔离、到期、已终结且token终结持久、dependencies_closed=true | 正文提交成功不证明恢复依赖已结束 |

每域deadline来自经批准的tenant策略与授权评估，不给通用“保留N天”伪精确默认。除index的非权威重建分支外，deadline未知、commit/持久终结/依赖未知都retain；所有域hold未知或授权未知都retain。已知hold必须阻止包括index在内的一切自动清理；不能用重建资格规避取证保留。

dependencies_closed来自完整血缘与恢复台账，涵盖仍在使用的派生前提、恢复引用、备份恢复需求与法律阻断，不以当前用户可见子图或引用计数为零替代。quarantined默认保留等待治理；不能靠purge移走悬空来源从而降密。superseded版本也受前提依赖约束。清理失败必须按记录域报告，不把局部成功宣称全介质擦除。

## 删除权利与幂等冲突

token_final保留不是声称无限留存合法；部署若有强制全部删除要求，必须先定义并验证token作用域永久关闭/旧客户端请求永拒、最小化不可复用终结证据或等价安全协议。首版没有该协议，阻止相关部署发布，不能一边删幂等历史一边仍声称exactly-once。

intent、审计与历史receipt的持久终结凭证必须匹配tenant/principal/operation/token/指纹，不能拿其它请求“已有终结”当清理凭据。模型boolean是假定证据可信；没有选定真实后端/签名/持久性证明，运行时清理资格无法成立。

## 恢复与物理介质

备份恢复先隔离，重放当前墓碑/策略和token终结账本再暴露内容；墓碑覆盖不全、代际未知或取消历史冲突时拒绝恢复发布。不能从旧备份复活forget或被撤销的权限/核验状态。

物理擦除涉及缓存、镜像、日志、备份及存储介质；加密擦除需密钥生命周期证据。eligible不证明擦除完成，外部服务副本需独立证明。实际执行另获数据授权与恢复计划，本次不触碰任何生产数据。
