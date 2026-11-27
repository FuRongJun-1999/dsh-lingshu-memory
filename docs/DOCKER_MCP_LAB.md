# Docker Linux MCP 接入实测

**独立协议客户端与官方 DSH 工具执行链是两项不同实测。** 影子服务仅以 stdio 提供受限工具 `shadow_request`，开放 `Write.create`、`Read.get`、`Read.search`、`Read.receipt`；主体由可信实验启动器选定，不接受请求传入的身份、权限、库路径或生产凭据。Bob 的服务实例拒绝写入；读取仍由文件库检查权限。两个实验工具挂到同一个测试注册表时，仅用于确定性对照，不是模型可见角色配置或多租户授权设计。

在仓根执行：

~~~text
python -X utf8 -B scripts/docker_mcp_lab.py
python -X utf8 -B scripts/docker_mcp_lab.py --with-dsh
~~~

第一个命令用 [独立客户端](<../scripts/linux_mcp_wire_lab.py>) 运行 MCP 初始化、工具发现、写入、拒读和重新打开。第二个命令用 [DSH 实际组件](<../scripts/linux_dsh_mcp_lab.mjs>) 启动 Cordis、官方 MCP 桥接、工具注册表和原生执行器：一次写入后真实强停 MCP 服务进程，等待自动重连，再查阅原正文、定位符和回执。两条路径均要求同 token 不重复追加审计、异内容冲突拒绝，并对照授权搜索、越权搜索与无匹配查询。

需本地已有 Linux 镜像：独立客户端用 `python:3.11-slim`，官方组件用 `node:24-bookworm`（同时提供 Node 及 Python）。不会自动拉镜像。官方组件复跑先在只挂载空任务依赖目录的容器，从公开 npm 按 [依赖锁](<../scripts/docker_mcp_package-lock.json>) 安装，禁生命周期脚本；**执行实验另起无网络、非 root、只读根容器**。源码与依赖均只读，数据仅在容器任务的 tmpfs 内；不挂载现有目录、凭据或 Docker socket。结果绑定镜像和源码摘要，不把未提交工作树当成远端提交。

隔离启动主体不是生产认证；该服务不是通用 MCP 后端。不声明已接入现用 GUI、已启用模型循环、模型会主动回取、跨容器保留数据、抗断电或具备生产资格。另有 [阶段强停实验](<DOCKER_PROCESS_LAB.md>) 核对事务提交前后的不同恢复结果。
