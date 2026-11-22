# 阶段台账（Stage Ledger）

本文件是**可机检**的阶段冻结记录：每一行对应一次已提交的候选、其验证读数、以及**当时被明确排除在外的结论**。
校验脚本：`scripts/ledger_check.py`（由 `scripts/check_all.py` 之外独立运行，CI 中由 `tests/test_stage_ledger.py` 调用）。

## 台账规则

1. 每行必须给出 40 位提交 id、测试总项数、以及 `independence` 上限。
2. `independence` 只能是 `I0`–`I4` 之一；**I0/I1 行不得出现 production/power 通过类结论**。
3. 行一旦写入不得修改（只可追加）；需要更正时追加新行并注明 `supersedes`。
4. `gates` 列只能是 `NOT_RUN`（生产运行时门禁）或 `BLOCK`（发布门禁），本仓库当前两者都是这两值。

## 冻结记录

| stage | commit | tests | independence | gates | 说明 |
|---|---|---|---|---|---|
| stage-0.1-v3 | ee422804cc18cb09685f2b99c260d903fcfb8a14 | 262 | I1 | NOT_RUN/BLOCK | 证据锚定提交字节、必需注册表、固定根、production 读回 |
| stage-0.1-v4 | 7e39884e176850b0d2e4a2a2e0250b998f4f256a | 262 | I1 | NOT_RUN/BLOCK | 外部钉住、ref 包含、正文失败标记、时间窗 |
| stage-0.1-v5 | 37c568715227ca1066a1ca2871265771a8bc572c | 268 | I1 | NOT_RUN/BLOCK | tz 硬化、ref 形态与钉住、base/drift、git 硬化、RESULT 行 |
| stage-0.1-v6 | 8cbfcda4c1557ae2c7a6d0c4114e88254c3538b9 | 274 | I1 | NOT_RUN/BLOCK | 纯标准库 Ed25519 与签名 attestation |
| stage-0.1-v7 | fac9cb4ab0833e6a0229a1b01352d8d174cbdf49 | 283 | I1 | NOT_RUN/BLOCK | 复核者签名、RFC 8032 向量回归 |
| stage-0.1-v8 | 0252c17c99ed765f80ec336616b2d79af41c90cd | 290 | I1 | NOT_RUN/BLOCK | 小阶点/单位元伪造修复、动态 CHECKS RUN |
| stage-0.1-v9 | 461d3795cb44a4686cb53f015fa2ddf318d53b37 | 294 | I1 | NOT_RUN/BLOCK | production 证据提交字节绑定与显式错误码 |

## 证据等级定义（与 SELF_ITERATION_VALIDATION.md §5 一致）

| 等级 | 含义 |
|---|---|
| I0 | 同一次会话、同一模型、同一上下文自评 |
| I1 | 不同上下文/不同模型复核，但**不执行**、不读原始字节 |
| I2 | 独立方在**自己的环境**执行门禁并核对提交字节 |
| I3 | 独立方使用**带外信任根**（签名注册表/CI 回执）复核 |
| I4 | 不同时间、不同组件、不同主体的延迟复现 |

## 当前边界声明（不得省略）

- 本仓库所有阶段门的 `PASS` 至多记 **I1**：`--trusted-key`、`--pin-*`、`--require-ref` 均来自**同一条命令行**，验证方与被验证方未分离；
- 因此 `PASS` **不得**用于 production/power 放行、`M6` 迁移判定、release gate 变更，也不得表述为“已独立验证”；
- 达到 I2 的必要条件：由独立方在其环境执行 `scripts/check_all.py` 并核对候选提交字节；
- 达到 I3 的必要条件：带外注册表或 CI 侧签名回执，且验证方不自行提供钉住值；
- 达到 I4 的必要条件：不同时间点、不同组件路径、不同主体的延迟复现，且三次结论一致。

## 已知共因风险

1. 全部复核与被复核对象由同一模型家族产生（共因失效风险）；
2. 测试与实现由同一方编写，变异体锚点也可能与实现同步漂移（已发生：`body`→`lowered_body`、`valid`→`attestation_valid` 撞车）；
3. 门禁脚本与被审仓库同仓同 PR，改动可同时触及两者；
4. 本机 `cryptography` oracle 交叉验证不进 CI，Verifier 互通性证据仅一次性。