# 模型默认输出长度与上下文容量

2026-10-23 更新：后台已启动并加载最新代码，`model_default_lengths: true` 已在线验证。后续修复与验收见 [运行修复记录](2026-10-23-runtime-repair.md)。本文“当前生效边界”和手动重启说明保留原检查时的状态及操作参考。

用户要求输出长度和上下文使用模型自身默认值。两项默认值均改为 `null`，不再默认填写 2048 / 32768。Chat Completions 默认不发送 `max_tokens` / `max_completion_tokens`，上下文由模型服务校验。手动长度覆盖仍可选，留空或点击“恢复模型默认”即可取消覆盖。

旧浏览器连接档案从版本 1 一次性迁移到版本 2，将所有连接的两项长度清空，保留提供商、地址、模型、推理强度、连接编号及会话密钥；之后新保存的显式覆盖不会被重复清空。预览显示“模型默认”，不捏造服务实际容量。旧后台不支持空值时，前端在生成前检查能力并提示重启，不发送生成请求。

Claude 原生 Messages 协议强制要求 `max_tokens`，默认从服务模型目录的 `max_output_tokens` 或 `max_tokens` 声明读取；缺少声明时提示手动填写，不猜测数字。参考：[DeepSeek 输出默认参数](https://api-docs.deepseek.com/api/create-chat-completion/)、[Claude Messages](https://platform.claude.com/docs/en/api/messages/create)、[Claude 模型元数据](https://platform.claude.com/docs/en/api/models/retrieve)。

验证：111 项相关后端测试、16 项相关前端测试通过，包含默认请求省略参数、显式覆盖、Claude 声明上限、缺少声明、存储迁移、会话密钥保留、旧后台拦截。Ruff、BasedPyright、Vue 类型检查及生产构建通过。浏览器确认两个数值框均为空、占位符为“模型默认”。未发送真实 LLM 请求。

## 当前生效边界

前端已更新。执行环境在命令运行前以 `blocked by policy` 拒绝了停止并重启 8001 后台的操作，重启命令没有执行。当前后台仍是旧进程，前端已明确提示重启。

## 手动重启

在原后台终端按 Ctrl+C，等待服务退出，再在 PowerShell 执行：

```powershell
Set-Location -LiteralPath 'D:\全球校园人工智能精英大赛\celllens-platform'
pwsh -NoProfile -File .\scripts\start_system.ps1 -ApiPort 8001 -StartLocalMysql -SkipBuild
```

若找不到原终端，可在自己的 PowerShell 中先执行以下检查和停止步骤，然后运行上面的启动命令。动态查找进程，不使用历史 PID；仅在所属工作目录、命令与空闲状态符合时停止。

```powershell
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'D:\全球校园人工智能精英大赛\celllens-platform'
$taskRepo = (Resolve-Path -LiteralPath '.').Path
$taskListeners = @(Get-NetTCPConnection -State Listen -LocalPort 8001)
$taskServerIds = @($taskListeners.OwningProcess | Sort-Object -Unique)
if ($taskServerIds.Count -ne 1) { throw '8001 端口进程不唯一，请手动核对' }
$taskServerId = $taskServerIds[0]
$taskServer = Get-CimInstance Win32_Process -Filter "ProcessId=$taskServerId"
if (-not $taskServer.CommandLine.Contains('backend.app.main:app') -or
    -not $taskServer.CommandLine.Contains('--port 8001')) { throw '不是预期 CellLens 后台' }
$taskCwd = & .\.venv\Scripts\python.exe -c 'import psutil, sys; print(psutil.Process(int(sys.argv[1])).cwd())' $taskServerId
if ($LASTEXITCODE -ne 0 -or (Resolve-Path -LiteralPath $taskCwd).Path -ne $taskRepo) {
    throw '进程工作目录不属于当前仓库'
}
$taskRuns = Invoke-RestMethod 'http://127.0.0.1:8001/api/v1/experiments?status=active'
$taskMeasured = Invoke-RestMethod 'http://127.0.0.1:8001/api/v1/measured/analyses?limit=100'
$taskResources = Invoke-RestMethod 'http://127.0.0.1:8001/api/v1/resources'
if ($taskRuns.total -ne 0 -or $taskMeasured.total -gt 100 -or
    @($taskMeasured.items | Where-Object {$_.status -notin @('completed','failed','cancelled','interrupted')}).Count -or
    $taskResources.active_cell) { throw '存在进行中的工作，请等待完成' }
$taskServer | Select-Object ProcessId, CreationDate, CommandLine | Format-List
Stop-Process -Id $taskServerId
```

启动后在另一个终端检查：

```powershell
(Invoke-RestMethod 'http://127.0.0.1:8001/api/v1/assistant/capabilities').model_default_lengths
```

应返回 `True`。浏览器 Ctrl+F5 刷新后，旧连接的长度自动迁移为“模型默认”。启动终端保持运行。
