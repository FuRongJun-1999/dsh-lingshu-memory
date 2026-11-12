# 响应与取消提案复核

独立设计复核给出三条有效反例：授权失败却重放原final泄漏存在性；committed+audit failed/unknown组合遗漏；fresh与cancel否定证据冲突。全部采纳：授权先于回放、审计四态表、冲突只查询。

本轮另发现上一版absent的首次应用资格过宽：恢复absent也可能来自已取消token。修正默认fail-closed、增加否定证据类别并保留取消/拒绝终结。改变的是未冻结API提案，核心冻结规则和恢复空盘unknown不变。

在线fresh_unseen不属于恢复absent，响应schema明确拒绝，只有内部受理谓词在同epoch临界区内可使用。代码小面复核返回空助手轮，不计为成功。设计意见由手工固定预期、负例和行为变异验证；不把这些等同独立代码证明。

验证仅覆盖元数据schema、响应组合、取消顺序证据、已终结token不复用、未授权元数据null、审计失败不重写。seal/fencing/CAS/持久性都是可信前提占位，所有真实运行时实验NOT_RUN。
