# Context与保留边界复核裁决

独立设计复核三项均采纳：clearance进入输出绑定；intent/body/backup清理显式要求恢复及前提dependencies_closed；分页输入cursor必须真实绑定当前身份/策略/快照，不接受旧cursor重盖代际。

模型进一步绑定实际response_sha与cursor_sha，逐字段相等、到期点严格拒绝；凭证、当前授权与cursor验证均严格bool且默认为外部可信证据，不从payload生成。

独立反例与变异覆盖clearance降权、主体/tenant/epoch/策略换代、实际输出页/查询/快照变更、到期、cursor拒绝、hold、active/隔离记录、未知期限、恢复依赖、token终结不可自动删除和audit独立义务。pure shape不是认证、eligible不是实际删除；实际输出TOCTOU和持久清理NOT_RUN。

整体范围独立复核确认方案与运行时分层一致，要求当前SHA重新绑定CI和代码终审失败显式裁决；全文与内联代码终审空助手轮均不计成功。采用规则独立复核+独立反例+变异的方案范围替代，不声称外部代码审计，详见[基线验收单](<../BASELINE_ACCEPTANCE.md>)。

此复核为规则级，不代替生产认证或法律审查。目标仍是公开可维护方案基线，未实现项登记后续门禁而不涂成PASS。
