# 固定旧操作兼容候选矩阵

仅覆盖顶层cg 39与stg 5 op，不覆盖action、参数组合或历史工具别名。全部runtime_ready=false；extension不是偷偷默认Read。

固定来源：[上游入口](https://github.com/FuRongJun-1999/dsh-memory/blob/b450d2f451ed33891e3f6587d238d1d4f5c9ecb9/md_cg/mcp_server.py)，SHA256 071eb877ba3a2bcb43fd01a8e9a367a9b3b3e69b26d3b4736f4e902a3aceeaba。仅解析AST，没有执行旧代码。

真源：[兼容清单](<../spec/compatibility.json>)。未知op/action拒绝；不推导默认op，不剥离调用方传入的未知字段后继续执行。

| 入口 | op | 候选层 | 源行 |
|---|---|---|---|
| cg | help | extension | 2551 |
| cg | write | Write | 2562 |
| cg | status | Read | 2568 |
| cg | edges | Read | 2571 |
| cg | theory | extension | 2574 |
| cg | link | extension | 2591 |
| cg | info | extension | 2731 |
| cg | route | Read | 2860 |
| cg | read | Read | 2883 |
| cg | audit | extension | 3073 |
| cg | goal | extension | 3144 |
| cg | task | extension | 3193 |
| cg | recent | extension | 3196 |
| cg | state_event | extension | 3235 |
| cg | state_view | extension | 3255 |
| cg | verify | extension | 3266 |
| cg | review | extension | 3272 |
| cg | forget | Govern | 3307 |
| cg | protect | extension | 3317 |
| cg | identity | extension | 3320 |
| cg | consistency | extension | 3323 |
| cg | metacognition | extension | 3326 |
| cg | self_state | extension | 3329 |
| cg | evolution | extension | 3332 |
| cg | sustain | extension | 3335 |
| cg | scrub | extension | 3338 |
| cg | predict | extension | 3341 |
| cg | causal | extension | 3344 |
| cg | whitebox | extension | 3347 |
| cg | index_code | extension | 3350 |
| cg | index_doc | extension | 3423 |
| cg | ref | extension | 3491 |
| cg | session | extension | 3494 |
| cg | ingest | extension | 3497 |
| cg | export | extension | 3500 |
| cg | maintain | extension | 3503 |
| cg | consolidate | extension | 3506 |
| cg | insight | extension | 3509 |
| cg | ccg | extension | 3512 |
| stg | relation | extension | 4214 |
| stg | timeline | extension | 4216 |
| stg | anchors | extension | 4223 |
| stg | consistency | extension | 4227 |
| stg | state_chain | extension | 4230 |

## 非自动等价映射

cg read包含get/search/recall及大量时间/角色视图参数；必须按已核对的shape明确分流，不能用node_id真假替代显式kind。route检索可有副作用，不能因映射Read就绕过状态变更审计。status/edges只有已授权视图可输出。

write的upsert/验证态/依赖与新Write.create/modify不等价；先区分新建与revision CAS，验证态另获Govern核验协议，缺token/reader ceiling不能补造。forget只支持明确治理请求，不自动继承全部旧forget子操作。

verify/review/protect等暂列extension：新Govern尚未定义核验审核权限与凭证协议，不能凭大类名称放行。stg relation/timeline/anchors/consistency/state_chain均扩展，不调用Read.search伪装实现。

旧默认时间轴不同：cg read effective（库层），edges observed，stg前四op observed；state_chain只有落账时间，不伪造效力轴。条件strict_conditions默认放宽不是新框架可继承的安全默认，迁移报告必须显式保留DEFER。

## 降级规则

能力名字只有在目标版本独立验证后才可声明支持；版本号大小或返回同名字段不能构成支持证据。缺当前授权/来源安全/条件时间语义任何必需能力就拒绝，不能用read_only绕开安全。仅缺写入能力而仍能安全读时才允许read_only；这不赋予用户读取权。
