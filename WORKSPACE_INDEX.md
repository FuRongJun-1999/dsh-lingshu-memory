# 工作区索引（生成）

先按职责定位文件；新增根目录/文件须改本脚本登记后重生成。

## 目录

- .github: 跨平台公开CI
- docs: 架构、恢复、安全、迁移与ADR
- framework: 纯参考模型，不是运行时
- sandbox_runtime: 显式隔离合成执行，不接生产
- scripts: 规格、索引、合规和门禁工具
- spec: 结构化契约真源与冻结锁
- tests: 独立预期样例与变异自证

## 根文件

- [.gitattributes](<.gitattributes>): 文本格式
- [.gitignore](<.gitignore>): 本地产物排除
- [CONTRIBUTING.md](<CONTRIBUTING.md>): 贡献与验证纪律
- [LICENSE](<LICENSE>): MIT许可
- [README.md](<README.md>): 项目入口与状态
- [SECURITY.md](<SECURITY.md>): 漏洞报告边界
- [WORKSPACE_INDEX.md](<WORKSPACE_INDEX.md>): 本生成索引

## 关键入口

- [规格](<spec/core.json>) / [生成规范](<docs/CONTRACTS.generated.md>)
- [模型](<framework/model.py>) / [测试](<tests/test_model.py>)
- [架构](<docs/ARCHITECTURE.md>) / [路线](<docs/ROADMAP.md>)
- [总门禁](<scripts/check_all.py>)
