# 条件与双时间保真提案

[纯规划模型](<../framework/migration.py>)与[手工固定预期](<../tests/test_migration.py>)只处理合成载体；不是旧库转换器，也未接入Write/Read schema。原有conditions文本数组不自动升级成新结构。

## 原始载体不能被“规范化”替代

legacy_capsule接收最多131072 bytes，保存原始base64、SHA256、编码识别与interpretation=DEFER。restore逐字节核对编码、摘要和RFC4648标准带padding无空白的canonical base64，不转换换行、浮点、Unicode或未知字段。非UTF8也保留bytes，不用replace解码。不向公开仓写任何实际旧库、capsule或生产原文。

base64不加密！capsule继承原始内容的敏感级别，只能在授权隔离区存储。摘要也不是授权证明；有完整控制权的攻击者同时改原文和摘要不在此模型防御范围。超限拒绝，不截断。

## 条件是声明，不是可执行代码

carrier/method/existence三项必须显式出现；每项是unknown，或declared+非空text（最多4096字符）。不把缺失当任意适用，不对文本eval，不从文本构造principal/权限。
carrier是载体/位置，method是适用方法，existence是存在约束；时间单列。模型仅验证声明形状并拷贝保真，不产生ACCEPT，也没有完整AND/OR/否定条件语言。未知条件不得作为放宽权限或宣称“确定适用”的依据。

## 双轴与精度

observed（观察/记录轴）和effective（效力轴）都必须显式存在，绝不互相回退。每轴有start/end，每个bound为：

- instant：value只允许真实UTC秒精度YYYY-MM-DDTHH:MM:SSZ；拒绝亚秒、偏移时区、epoch数值、非法日期和闰秒。
- unbounded：明确无界，不能带value。
- unknown：未知，不能带value；不是无界。

区间半开[start,end)，已知start>end拒绝，start=end为空集。point<start或point>=end已能确定NO_MATCH，即使另一端unknown；否则有未知返回DEFER，两端已知覆盖才MATCH。MATCH只指所选时间轴的数学点归属，不表示条件满足、内容真实或读取授权。

旧valid_from/valid_until、time_window、时间戳和比较算子保留原文，未选择逐字段转换政策之前DEFER，不能自动舍入到秒或把旧闭区间当新半开区间。stg state_chain没有第二轴，迁移不得伪造effective=observed。

## 降级判定

read_required/write_required来自经审核的部署能力profile，不能由外部payload删除要求。两个列表不得空；必需读能力包括tenant/当前授权/安全血缘/条件/双轴/策略代际，示例不是穷尽清单。
缺任何必需读能力=reject，未知=defer；全部读能力支持后，缺写能力可read_only，写能力未知=defer；全部已验证才eligible_isolated_shadow，仍不是生产切换许可。read_only也必须当前授权，不意味着解密/解封历史记录。资格判定不是授权检查：实际入口须先认证，授权false拒绝，unknown/缺失身份阻断并保持未决，任何分支都不能执行读写。

后续仍需审计完整profile、每个旧action/字段转换、网络适配器、数据授权、权限保留、兼容差异查询与物理回滚实测。未知不能靠降低要求消除。
