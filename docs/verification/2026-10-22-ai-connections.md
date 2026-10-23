# 大模型连接配置验收

日期：2026-10-22。范围：设置页与辅助解读的连接、目录获取、导入/导出及推理/上下文预算。不改变 STATE 推理、实测来源或科学产物。

## 已实现

- 最多 20 组命名连接，保存、切换、移除；旧单连接偏好迁移。非秘密参数保存 localStorage，密钥按连接保存在当前标签页 sessionStorage。没有对应会话密钥的连接不会借用其他连接的旧密钥。
- 获取服务端模型列表，与生成测试分开；支持搜索、手填、分页/数量限制、取消和防止跨服务迟到响应。读取明确的上下文元数据，不从名字推断能力。
- 通用平铺 JSON、数组/多连接 JSON、常见别名和 `.env` 文件/粘贴导入。先预览再加入新连接；导入不联网、不覆盖旧连接。文件解析不回显密钥到文本框；未知字段提示忽略。导出当前/全部及模板均不含密钥。
- 按提供商验证、映射推理选项；Claude 预算/自适应模式；服务默认省略参数。空密钥仅支持自定义兼容服务。保留服务 origin 允许列表及密钥错误脱敏。
- 上下文窗口与输出预算分别配置；真实预览显示 UTF-8/3 估算，后端发送前验证，超限不截断证据。预算元数据不纳入科学证据哈希或模型科研上下文。
- README、配置指南、API 文档及 OpenAPI 同步。

## 验证

| 检查 | 结果 |
|---|---|
| `.venv/Scripts/python.exe -m pytest backend/tests -q` | 424 passed，7 个依赖/测试数据警告 |
| 最后一次辅助解读专项回归（assistant / connections / measured / figures） | 96 passed，2 个依赖弃用警告；包含预算元数据不外发检查 |
| `node --test scripts/test-model-config.mjs scripts/test-measured-assistant.mjs`（frontend） | 12 passed；导入解析、导出不含密钥、偏好迁移、跨连接会话隔离及既有解读回归 |
| `npm.cmd run typecheck`（frontend） | 通过 |
| `npm.cmd run build` 与最终 `build:if-needed` | 成功；最终确认输入未变并复用已验证构建。保留既有 Three.js 分块 >500 kB 提醒 |
| 本次修改范围 Ruff / Basedpyright | 通过 |
| `python scripts/check_model_connections_frontend.py --url http://127.0.0.1:8001` | 主服务通过，模拟外部请求；搜索/选择、参数实际发送、导入两种方式、导出、刷新、切换、错误、迟到响应、亮暗主题，1920/1440/1280/1024 桌面宽度无页面横向溢出，无 pageerror |
| 真实记录只读预览 | 已完成 run 和 measured 摘要均返回预算信息、来源哈希及 no-store |
| 真实实测结果页预算显示 | 估算 4676 输入 token，与后端字节口径一致；未配置模型时禁止生成 |
| 真实接口预算拦截 | 声明窗口 4096、输出 4095，已知摘要输入大于剩余 1 token；返回 422 / CONTEXT_BUDGET_EXCEEDED，未访问外部模型 |
| 主服务新接口 | capabilities 提供推理选项；OpenAPI 注册 models；恶意域名目录请求联网前返回 ENDPOINT_REJECTED，错误无密钥且 no-store |

受控浏览器曾发现文件解析后预览被异步 watch 清空，已改为同步清理并直接解析文件内容；回归验证通过。项目现有全站最小宽度为 1024px，因此这里验收桌面范围，不声明移动端全站适配。

最初全量测试收集时，同目录另一项修改尚未生成 catalog_snapshot 模块；待文件写入后完整重跑得到上述 424 passed。构建期间源码有变动的一次缓存校验拒绝也已通过稳定源码后的重新构建解决。

## 主服务与边界

重载前核对本仓库 Uvicorn 8001 的进程身份，预测活动任务 0、5 条实测记录均无活动任务；仅停止该 API 服务并重启到同一端口。新 PID **24580**，绑定 **127.0.0.1:8001**；本任务启动的终端会话 **3695** 保持运行。MySQL 未重启。

证据：`reports/ai-settings-2026-10-22/browser/evidence.json`、亮暗截图、`export-without-secrets.json`、`live-context.json`、`live-budget.json`。源码修改前快照在同目录 `before/`，仅源文件与文档，不含浏览器密钥。

没有使用真实厂商 API Key，没有发起真实外部生成；模拟协议验证不代表账户权限、厂商可用性或回答科学质量已验证。通用导入不覆盖所有客户端私有备份格式；推理参数仍受模型支持限制。窗口估算不是实际 tokenizer，不扩展模型容量，也不增加摘要的科学证据范围。
