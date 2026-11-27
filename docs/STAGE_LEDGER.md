# 阶段台账（Stage Ledger）

本文件是**可机检**的阶段冻结记录：每一行对应一次已提交的候选、其验证读数、以及**当时被明确排除在外的结论**。
校验脚本：`scripts/ledger_check.py`，已接入 `scripts/check_all.py`（CI 会跑），并由 `tests/test_stage_ledger.py` 覆盖。

## 台账规则

1. 每行必须给出 40 位提交 id、测试总项数、以及 `independence` 上限。
2. `independence` 只能是 `I0`–`I4` 之一；**I0/I1/I2 行不得出现 production/power 放行、`M6` 迁移判定或 release gate 变更类结论**——这类结论要求 `I3` 及以上（见 `docs/EXTERNAL_ANCHORS.md`），且提级须先补设施、再改 `MAX_GRADE`（当前 `I1`）。
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
| stage-0.1-v15 | ec7d66021284fa2746d388fb2adb50fe072d9fae | 325 | I1 | NOT_RUN/BLOCK | 台账滞后检测 MAX_LAG=6 |
| stage-0.1-v16 | 537ee8ddeb4b00bdf8f76b05a5cd1cab44a7a89b | 328 | I1 | NOT_RUN/BLOCK | 外部锚清单与机检约束 |
| stage-0.1-v17 | 2c69ff0a7d3cc6324111ef05ba979a4c67f72752 | 333 | I1 | NOT_RUN/BLOCK | 组件级复核修复：真负例、fail-closed、复核台账 |
| stage-0.1-v18 | 9d7933b8fe8265dbcca431ff80d77639876d65a1 | 336 | I1 | NOT_RUN/BLOCK | 同形字折叠与行为级接线断言 |
| stage-0.1-v19 | e5cbe8ee2cca634c665a0f4cb3127fb0309a4319 | 338 | I1 | NOT_RUN/BLOCK | 复核签名与证明的域分离 |
| stage-0.1-v20 | a250e1ef7e6d6a443da84cedfedd83fd967a1699 | 341 | I1 | NOT_RUN/BLOCK | 阶段冻结说明与三节机检 |
| stage-0.2-v1 | 2bfd549bb3abb77a3e46f03135dd1fd6942bb713 | 345 | I1 | NOT_RUN/BLOCK | 同一主体复验 Docker 三条隔离路径与完整门禁；不提升证据等级 |
| stage-0.2-v2 | dce2ced23b34513cb3efdfb5d062dd6828e4630b | 350 | I1 | NOT_RUN/BLOCK | 按标识回读独立化；四矩阵及 Docker 两条接入路径 |
| stage-0.2-v3 | a4d69ecaff604b3f1bdad9351f765c6d22d0cf3d | 355 | I1 | NOT_RUN/BLOCK | 候选检索独立化，冻结排序与两条 Docker 对照 |
| stage-0.2-v4 | 14a795ca66ccc252b09f6a8ce2e73ceb7b4b872c | 358 | I1 | NOT_RUN/BLOCK | 写入幂等裁决隔离验收，三条 Docker 复验 |
| stage-0.2-v5 | ef0334dc3f974b2f57a605068f3d9c17cbce3123 | 362 | I1 | NOT_RUN/BLOCK | 治理与恢复方向独立化；文件事务在容器中实测 |
| stage-0.2-v6 | b14845f4987c022775a916d35641f527d8c9be51 | 364 | I1 | NOT_RUN/BLOCK | 主动取用核心解耦，冻结调用轨迹和容器实测 |
| stage-0.2-v7 | 404944e761ec48886d9f85585079817cfc961280 | 370 | I1 | NOT_RUN/BLOCK | 文件端口实测与共享实现行数机检 |
| stage-0.2-v8 | 63e3db5c6072fdd56148126fc16257be7a47b85b | 372 | I1 | NOT_RUN/BLOCK | 冻结旧入口与隔离能力覆盖对照 |
| stage-0.2-v9 | 2281e11580a8b2f37c56c193d96f9af826f16d98 | 375 | I1 | NOT_RUN/BLOCK | 版本绑定证明子集与容器复验 |
| stage-0.2-v10 | 0ea1bc313a90182e2edaa075c1b20b1924485904 | 378 | I1 | NOT_RUN/BLOCK | 授权节点核验态与容器复验 |
| stage-0.2-v11 | f4866e5ac78b2dfbd82bb5e4e8a75374d0015f9a | 381 | I1 | NOT_RUN/BLOCK | 授权来源出边投影及容器复验 |
| stage-0.2-v12 | 8fe5c3256ecba2f8d4e00111ded26040a201f93b | 384 | I1 | NOT_RUN/BLOCK | 授权双节点时间关系，三容器及四矩阵 |
| stage-0.2-v13 | 64a8bd2b89f3a0ed78cbf29518c3de10ed5b5b03 | 387 | I1 | NOT_RUN/BLOCK | 显式时点授权时间线及容器/四矩阵 |
| stage-0.2-v14 | de0e8a01cc5e2851a3f65fe23eac02c368253861 | 390 | I1 | NOT_RUN/BLOCK | 授权时间窗锚点及容器和四矩阵 |
| stage-0.2-v15 | 9732a0eaeca9814c4d7bffa6298e9d165903612f | 393 | I1 | NOT_RUN/BLOCK | 单节点时间检查与公开四矩阵 |
| stage-0.2-v16 | 617949909dc131ead74b6ae9857e52559f160754 | 397 | I1 | NOT_RUN/BLOCK | 受信单槽状态投影与容器四矩阵 |
| stage-0.2-v17 | d6d5af66fadefd6f307cdbb9555f7feed77b8e37 | 401 | I1 | NOT_RUN/BLOCK | 授权单槽状态事件追加与跨进程验收 |
| stage-0.2-v18 | 61125c806d971bb0fe49666112b230b64ff22669 | 404 | I1 | NOT_RUN/BLOCK | 单槽租约、到期边界及容器/四矩阵 |
| stage-0.2-v19 | b2bae6bd470b3fd13f43464656a4992b7404c6e8 | 407 | I1 | NOT_RUN/BLOCK | 授权节点证据审计与公开四矩阵 |


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