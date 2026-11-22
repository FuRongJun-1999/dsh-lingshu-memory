# 阶段冻结说明（Stage Freeze）

本文件是 `stage-0.1` 这一轮自指验证的冻结记录：说明**冻结了什么、证明了什么、明确没有证明什么**。它由 `scripts/ledger_check.py` 机检（必需小节、I1 上限字样、指向外部锚清单），并与 `docs/STAGE_LEDGER.md`、`docs/EXTERNAL_ANCHORS.md` 互为约束。

## 冻结范围

- 冻结对象：`scripts/stage_gate.py`（阶段门）、`scripts/ed25519.py`（签名）、`scripts/ledger_check.py`（台账校验）、`docs/STAGE_LEDGER.md`、`docs/REVIEW_LOG.md`、`docs/EXTERNAL_ANCHORS.md`。
- 冻结区间：台账 `stage-0.1-v3` 至当前末行；每行绑定一个提交，行与提交内容由 `artifact` 检查绑定，台账落后超过 `MAX_LAG` 个提交即失败。
- 冻结含义：**在该提交上、按该命令跑出的结论可以被逐位复算**；不代表系统可用于生产。

## 已证明

1. 阶段门对证据、钉住值、时间窗、等级、复核签名、生产证据的检查，在给定提交字节上是确定性的，且每条检查都有对应变异测试（变异存活即为测试失败）；
2. 签名实现通过 RFC 8032 测试向量，并拒绝小阶点、`s >= L`、长度不符与无域签名；
3. 台账、复核日志、外部锚清单三者均由同一校验器机检，措辞检查经 NFKC + 零宽去除 + 同形字折叠，撤词（删除黑名单）会被单独检出；
4. `check_all.py` 以模块级命令表执行各门禁，台账校验的行为由子进程退出码断言。

## 未证明

1. **独立性**：全部复核与被复核对象同源（同模型家族、同会话时段、注入文本），等级上限 `I1`；
2. **跨环境可复现**：没有任何一次执行发生在第二个环境，测试全部同机串行；
3. **密钥归属**：`--trusted-key` 与钉住值来自同一条命令行，签名只证明“某密钥签了这段字节”；
4. **生产适用性**：production / power 门禁为 `NOT_RUN`，release gate 为 `BLOCK`，`M6` 迁移未执行。

## 禁止的结论

- 不得把本冻结表述为“已通过生产验收”“可上线”“生产可用”“已独立验证”；
- 不得据此变更 release gate、执行 `M6` 迁移试点或切换服务；
- 不得在 `independence` 记 `I2` 及以上——除非先按 `docs/EXTERNAL_ANCHORS.md` 补齐设施并留下可复核回执。

## 如何复算

```
python -B scripts/check_all.py            # 全部门禁 + 全仓测试
python -B scripts/ledger_check.py         # 台账/复核日志/外部锚 单独校验
python -B -m unittest discover -s tests   # 全仓测试
```

复算结论只对该次检出的提交成立；提交变化后须重新复算，台账须同步追加行。

## 已知缺口（与复核日志一致）

1. 台账行与提交内容只绑定“该提交存在门禁与校验脚本”，未核对该行声称的测试数来自该提交的 RESULT 行；
2. `append-only` 无强制机制，仅靠祖先序 + 行数下限 + 滞后上限，历史改写需人工审阅；
3. `check_all` 末尾的 `PRODUCTION RUNTIME GATES: NOT_RUN` 是静态输出，不来自运行时状态；
4. 措辞检查是黑名单策略，未覆盖全部 Unicode 混淆集，也未覆盖 commit message 与生成物。