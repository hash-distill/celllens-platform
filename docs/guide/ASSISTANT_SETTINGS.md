# 外观与大模型辅助解读

右上角“设置”进入 `/settings`。右侧快捷栏提供亮暗切换、直达顶部、直达底部、设置和使用说明；窄屏显示在左下方，AI 解读入口位于右下方。主题可以选择浅色、深色或跟随系统，偏好保存在当前浏览器。科学图的数据配色与导出内容保持原有语义。

## 配置连接

1. 选择 OpenAI、Gemini（Google）、Claude（Anthropic）、DeepSeek、硅基流动或自定义兼容服务。系统从后端获取提供商选项，自动填写对应基础地址和接口参数；切换时清空模型和密钥输入，请填写当前提供商的准确模型 ID 与 API Key。
2. 基础地址包含服务需要的前缀，不包含末尾请求路径。Gemini 使用 `https://generativelanguage.googleapis.com/v1beta/openai`；Claude 使用 `https://api.anthropic.com/v1`。“高级选项”可调整最大输出长度，默认 2048 token；CellLens 当前允许 256–8192，仍需符合所选模型的限制。token 是模型处理文本的单位，不等于字数，也不是输入上下文长度。达到上限时回答可能截断，部分推理模型将思考 token 计入上限。OpenAI 与自定义兼容服务可以调整输出长度参数，其他提供商自动匹配参数。
3. “测试连接”发送一条简短消息，可能消耗服务额度。连接成功后保存配置。
4. 打开已完成的扰动实验，在右下角“AI 解读”悬浮框选择任务、预览摘要，再点击“发送摘要并生成解读”。

当前提供商、服务地址、模型和输出长度保存在当前浏览器 localStorage；保存后作为当前解读连接。API Key 保存在当前标签页的 sessionStorage，并在请求期间暂存于后端内存；不写入共享数据库、运行清单或分析文件。刷新页面仍可使用；浏览器恢复会话或复制标签页可能保留密钥。离开共享设备前请点击“清除 API Key”。浏览器禁止存储时，配置仅在当前页面内生效。多用户远程部署应通过 HTTPS 提供网站。旧版配置会保留，并根据地址识别已有提供商。

| 提供商 | 默认基础地址 | 请求方式 |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | Chat Completions |
| Gemini（Google） | `https://generativelanguage.googleapis.com/v1beta/openai` | 官方 OpenAI 兼容接口 |
| Claude（Anthropic） | `https://api.anthropic.com/v1` | 原生 Messages 接口 |
| DeepSeek | `https://api.deepseek.com` | Chat Completions |
| 硅基流动 | `https://api.siliconflow.cn/v1` | Chat Completions |
| 自定义兼容服务 | 手动填写 | Chat Completions |

## 发送内容与结果

系统从当前已完成记录生成摘要，校验所读取产物的登记哈希。在线结果包含来源、表达单位合同、摘要中的前 20 行基因和代谢任务，以及可用的官方完整性总体统计。前 20 行沿用已保存报告顺序，不是完整结果或重新进行的统计筛选。

摘要不包含逐细胞表达矩阵、PCA 坐标或源文件路径。细胞背景和扰动目标仍属于结果摘要的一部分，发送前应检查页面中的完整预览。生成时再次核对摘要 SHA-256，内容发生变化会要求重新预览。

可选任务为主要结果解读、覆盖与局限说明、后续科研验证建议。大模型输出作为独立纯文本展示，不修改原始科学结果、任务状态或数据。生成文本可能错误，不能代替原始证据、显著性检验或生物学验证；覆盖不等于准确率，scCellFie 分数不等于实测通量。解读仅保留在当前页面，可下载包含模型、时间、来源、摘要哈希和服务返回 token 用量的 JSON。

## 自定义与本机服务

默认允许 OpenAI、Gemini、Claude、DeepSeek 与硅基流动的上述官方 origin。其他服务由管理员在 `.env` 中登记**完整 origin**（协议、主机及端口，不带路径），重启后端后生效：

```dotenv
CELLLENS_ASSISTANT_EXTRA_ORIGINS=https://models.example.org,http://127.0.0.1:11434
CELLLENS_ASSISTANT_TIMEOUT_SECONDS=90
```

设置页面会列出当前允许范围。用户可将基础地址填写为 `http://127.0.0.1:11434/v1`；这里的本机是运行 CellLens 后端的机器。额外地址由部署者信任并管理，避免加入不受控域名或敏感内网服务。前端不能修改部署的数据库、GPU、文件路径和资源限制。

后端不跟随重定向、不读取代理环境变量、不自动重试；单进程最多同时处理 2 个大模型请求，请求体不超过 64 KiB、摘要不超过 48,000 字节、响应不超过 128 KiB，超时配置范围 5–90 秒。错误提示不会返回上游错误正文或密钥。兼容接口不包含工具调用、自动执行或模型训练。

协议参考：[OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)、[Gemini 官方兼容接口](https://ai.google.dev/gemini-api/docs/openai)、[Claude Messages](https://platform.claude.com/docs/en/api/messages/create)。服务商的具体模型可用性、额度、数据保留和 token 参数以其文档为准。

设置设计参考 [Chatbox 的提供商注册与默认配置](https://github.com/chatboxai/chatbox/blob/main/docs/technical/ai-providers.md)和 [Open WebUI 的连接设置](https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/)：集中管理提供商默认地址和协议，按提供商填写密钥、模型及地址。设置页只保留外观与大模型连接，部署环境在服务状态页查看。CellLens 当前保存一组活动连接，尚未实现这些项目的完整多连接管理与远程模型发现功能。

## 为什么不同实验的覆盖数字相同

官方完整性依据本次基因面板的名称和冻结代谢库计算，不使用表达量判断基因是否包含在面板中。同一面板和数据库会产生相同的覆盖数字；改变扰动、细胞数或随机种子可以改变表达与任务分数，但不会扩展模型的输出基因范围。代谢库基因覆盖表示数据库基因中有多少包含在面板中，“全部关联基因完整覆盖的任务”表示任务关联基因是否齐全，不表示任务受扰动影响或预测正确。

当前数字可用 `.venv/Scripts/python.exe -m scripts.audit_current_coverage` 对已完成在线实验重新核对；脚本检查保存产物的清单哈希、独立计算基因集合交集，并从本地冻结数据库重新计算官方完整性，只读取实验数据。
