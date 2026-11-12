# 开发运维与发布边界

## 门禁

在仓库根运行python scripts/check_all.py；公开提交前再独立执行public_guard。命令使用argv、UTF-8、PYTHONUTF8=1、shell=False，保留退出码；日志留本地，不提交原始会话。新增文件在未跟踪状态不会被普通git diff --check覆盖，必须在明确候选暂存后运行git diff --cached --check；暂存门禁非零不提交。

## Git网络兜底

Git HTTPS不可用但GitHub REST可用时，可用Git Objects API上传已验证候选。每个blob摘要与本地对象一致，最终tree必须与本地已验证tree一致；更新ref前再查询当前SHA，禁止force。
空仓Git Objects API可能返回409，需要先用已审查的README通过Contents API初始化；保留初始化历史再发布完整树。
此时远端commit会因parent不同而与原本地commit不同，但tree应相同。必须分别报告两者，不说commit SHA一致。
请求结果未知先读取远端ref/对象，不能换请求盲目重发或覆盖他人变更。恢复后本地与远端历史需显式对账，不用reset --hard掩盖分歧。
不把REST API可用当成Actions已通过；CI需绑定发布commit并收取全部矩阵结论。

## 不属于自动操作

生产迁移、服务切换、真实数据清理、密钥与个人信息公开、绕过受保护分支规则。任何这些事项都须另获授权。
