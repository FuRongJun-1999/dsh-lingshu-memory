# Docker Linux 实测：进程强停与恢复

仓根执行 `python -X utf8 -B scripts/docker_process_lab.py`。需要已存在的 Linux 镜像 `python:3.11-slim`；脚本不拉取镜像。只复制本任务所需的源码/规格到临时目录，挂载为只读。容器不联网、以非 root 运行、根文件系统只读，仅临时内存文件系统可写。不挂载现有记忆库、宿主配置、凭据或 Docker socket。输出包括镜像 ID、实际输入字节摘要和是否为未提交工作树；不得只凭 base 把它标成提交验证。

[强停实验](<../scripts/linux_process_kill.py>)以子进程发出的阶段回执定位 SIGKILL，不用 sleep 猜窗口；核对真实退出码 -9、恢复 PID 不同、原正文与定位符、回执原写者、审计行数和拒读不带记录。

| 关键窗口 | 预期恢复 | 审计行数 |
|---|---|---:|
| manifest 替换前 | unknown；不能重复写；无可读正文 | 0 |
| manifest 替换后 | committed；回放原写者的回执 | 1 |
| 审计追加后 | committed；不追加重复审计 | 1 |

这是 Docker Linux 进程级实验。文件跨进程保留，但容器结束后临时数据销毁；不用它宣称磁盘跨重启、VM 停机、断电持久化、真实 DSH 接线、生产鉴权、生产或 power 验收。证据等级不因 Docker 自动提级。

同一实验也对合成 Govern.forget 执行三窗口强停。提交前维持可读、回执 unknown、只有初始化写入的审计行；提交后正文文件仍在但不可读，回放原治理回执，审计总计两行。其他三种治理动作仍只覆盖本地故障注入。
