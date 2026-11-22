# 阶段台账（Stage Ledger）

本文件是**可机检**的阶段冻结记录：每一行对应一次已提交的候选、其验证读数、以及**当时被明确排除在外的结论**。
校验脚本：`scripts/ledger_check.py`，已接入 `scripts/check_all.py`（CI 会跑），并由 `tests/test_stage_ledger.py` 覆盖。

## 台账规则

1. 每行必须给出 40 位提交 id、测试总项数、以及 `independence` 上限。
2. `independence` 只能是 `I0`–`I4` 之一；**I0/I1 行不得出现 production/power 通过类结论**。
3. 行一旦写入不得修改（只可追加）；需要更正时追加新行并注明 `supersedes`。
4. `gates` 列只能是 `NOT_RUN`（生产运行时门禁）或 `BLOCK`（发布门禁），本仓库当前两者都是这两值。
5. 行必须按提交祖先序排列（后一行的提交须包含前一行的提交），以此检出历史改写与插队。
6. 每行的提交里必须确有 `scripts/stage_gate.py`（行与提交内容绑定，防止追认伪造阶段）；`tests` 必须为正且单调不减。
7. 行数不得少于 12 行（`MIN_ROWS`），防止“只留好看的行”。
8. 台账不得落后超过 6 个提交（`MAX_LAG`），否则报 `ledger_stale`——防止“台账停在旧阶段”。

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
| stage-0.1-v10 | 58d02a9af58dc3170c4c6f53b7d45ab1f5758aa2 | 300 | I1 | NOT_RUN/BLOCK | 可机检阶段台账与证据上限声明 |
| stage-0.1-v11 | 4ed9d8b4e6902c3ef60ddf0bbe2f65bb193363bb | 301 | I1 | NOT_RUN/BLOCK | 台账入主链与祖先序校验 |
| stage-0.1-v12 | 2c0403dc6a866e6a94a3e688488f1d5ff2fe4d8c | 316 | I1 | NOT_RUN/BLOCK | 等级上限 I1、措辞归一化、22 分支覆盖 |
| stage-0.1-v13 | c7ce8a47c8afd23c73a0d29ae2b1d4f4b3179c18 | 319 | I1 | NOT_RUN/BLOCK | 台账行与提交产物绑定、测试数单调 |
| stage-0.1-v14 | e4dc23ee7e845387ad9864707935f87ac5294d6c | 323 | I1 | NOT_RUN/BLOCK | 全文档越界声明扫描与撤词检测 |

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