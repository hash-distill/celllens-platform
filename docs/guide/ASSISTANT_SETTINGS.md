# AI 科研解读与模型设置

更新日期：2026-10-22。右侧快捷栏的星光按钮打开 AI 科研解读侧栏，设置按钮进入 `/settings` 配置模型。结果页与侧栏并排展示，可继续选择图表指标。顶栏仍提供亮暗切换和服务状态。

## 配置连接

1. 在“当前解读连接”中选择已保存的连接，或点击“新建连接”。最多保存 20 组，可按用途命名。切换到保存的连接会应用该连接；请先保存编辑中的内容。
2. 选择 OpenAI、Gemini（Google）、Claude（Anthropic）、DeepSeek、硅基流动或自定义兼容服务。按提供商自动填写默认地址和接口参数；更换提供商会清空旧模型和密钥。云端服务填写 API Key，自定义兼容服务允许空密钥，以支持无需认证的本地推理服务。
3. 填写服务基础地址，可直接粘贴完整 `/chat/completions` 或 `/messages` 地址，系统整理末尾路径。Gemini 使用 `https://generativelanguage.googleapis.com/v1beta/openai`；Claude 使用 `https://api.anthropic.com/v1`。页面展示实际生成请求地址和部署允许范围。
4. 点击“获取模型列表”，搜索并选择文本对话模型，也可手动填写准确模型 ID。此操作只查询模型目录，不发送科研摘要。服务不提供目录时不会妨碍手填或测试；目录中的图像、嵌入模型不一定适合文本解读。列表存在不代表生成已通过测试。服务明确返回 `context_window` 时显示声明容量；默认由服务管理，不根据名称猜能力。
5. 调整生成参数，点击“测试连接”。测试发送简短消息并使用所填参数，可能消耗服务额度。测试成功后“保存配置”。未保存的字段只影响本页测试，不替换右侧解读的活动连接。
6. 打开已完成的实测分析或预测结果，从右侧栏“AI 解读”选择任务、预览发送内容，再点击“发送摘要并生成解读”。预测科研图还可点击“解读此图”。

各连接的提供商、服务地址、模型和生成参数保存在当前浏览器 localStorage。API Key 按连接分别保存在当前标签页 sessionStorage，并在请求期间暂存于后端内存；不写入共享数据库、运行清单、分析文件或配置导出。刷新页面仍可使用；浏览器恢复会话或复制标签页可能保留密钥。离开共享设备前请逐个清除会话密钥或关闭会话；“移除当前连接”同时删除该连接的会话密钥。浏览器禁止存储时，配置仅在当前页面内生效。多用户远程部署应通过 HTTPS 提供网站。旧版单连接偏好会迁移；没有对应会话密钥的连接需要重新填写，不会挪用其他连接的密钥。

## 通用配置导入与导出

“导入配置”支持选择文件或粘贴内容。解析和预览在浏览器内完成，不发送网络请求；核对地址后点击“导入为新连接”，保留原有连接。文件最多 64 KiB，一次最多 20 组，导入后总连接数也不超过 20。导入完成仍需按需测试，地址不会自动进入部署允许列表。

通用平铺 JSON 示例（也支持 `baseURL` / `baseUrl`、`apiKey`、`modelId`、`maxTokens` 等常见别名）：

```json
{
  "name": "科研解读",
  "provider": "custom",
  "base_url": "https://models.example.org/v1",
  "api_key": "",
  "model": "your-text-model",
  "reasoning_effort": "auto",
  "max_tokens": null,
  "context_window": null
}
```

`.env` 示例（作为导入文件，**不是**把密钥写入 CellLens 后端 `.env`）：

```dotenv
AI_CONNECTION_NAME=科研解读
AI_PROVIDER=custom
OPENAI_BASE_URL=https://models.example.org/v1
OPENAI_API_KEY=
OPENAI_MODEL=your-text-model
AI_MAX_TOKENS=2048
AI_CONTEXT_WINDOW=32768
AI_REASONING_EFFORT=auto
```

也支持 `AI_BASE_URL` / `AI_API_KEY` / `AI_MODEL` 以及 `BASE_URL` / `API_KEY` / `MODEL`。环境文件只作为数据解析，不执行脚本、命令或变量替换；`${VARIABLE}` 等须先替换成实际值。可导入 JSON 数组或 `{"connections":[...]}`。本系统导出采用 `format: "celllens.ai-connections", version: 1` 的多连接 JSON；“导出当前配置”和“导出全部”均不含密钥。下载模板从当前版本生成。通用接入配置不等于能解析所有第三方客户端的完整备份或私有格式；不支持的字段会提示忽略。

## 推理强度、思考预算和上下文

- 默认“服务默认”省略推理参数，保持普通文本模型兼容。非默认强度须由具体模型支持，选项不会自动证明能力；服务拒绝参数时，恢复默认或核对型号文档。
- OpenAI / 自定义兼容接口使用 `reasoning_effort`；Gemini 按其兼容接口提供 `none/minimal/low/medium/high`，部分 Gemini 型号不能关闭思考。DeepSeek 使用 `thinking.type` 控制开关，启用时结合 `reasoning_effort: low/high/max`。硅基流动各模型扩展不统一，目前只使用服务默认。
- Claude Messages 支持默认、关闭、预算思考和自适应思考；预算思考发送 `thinking: {type: "enabled", budget_tokens: N}`，最少 1024 且小于最大输出；自适应发送 `thinking: {type: "adaptive"}`。显式强度使用 `output_config.effort`，须结合支持的思考模式/型号。较旧模型可能不支持自适应或 effort。
- 最大输出长度默认留空（`null`），Chat Completions 请求省略 `max_tokens` / `max_completion_tokens`，使用模型服务默认值。Claude 原生接口要求输出上限时，读取服务目录中所选模型的声明上限；未声明则提示手动填写，不猜固定数值。手动指定范围为 256–2,000,000 token；服务实际能力及响应读取上限仍独立生效。
- 上下文窗口默认留空（`null`），由模型服务按实际容量校验。需要额外限制时可手动填写 4096–2,000,000 token，平台才对输入与已指定输出预算进行估算拦截。输入估算始终可见，模型默认容量不伪造为固定数值。
- 手动限制超出时后端在联网前提示调整，不截断科学证据。上下文只包含本次系统提示、任务、补充问题和经核验的摘要，不增加对话历史或原始矩阵。设置更大的窗口不会让前 20 行摘要变成全量分析。

| 提供商 | 默认基础地址 | 请求方式 |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | Chat Completions |
| Gemini（Google） | `https://generativelanguage.googleapis.com/v1beta/openai` | 官方 OpenAI 兼容接口 |
| Claude（Anthropic） | `https://api.anthropic.com/v1` | 原生 Messages 接口 |
| DeepSeek | `https://api.deepseek.com` | Chat Completions |
| 硅基流动 | `https://api.siliconflow.cn/v1` | Chat Completions |
| 自定义兼容服务 | 手动填写 | Chat Completions |

## 发送内容与结果

若提示模型返回空正文，表示服务没有返回正式解读；仅凭旧提示不能判断是否耗尽输出预算。默认已改用模型服务的输出长度与上下文容量，现有连接刷新时一次性清除旧版固定长度。若曾手动指定较小预算，可点击“恢复模型默认”并保存，再重新预览和发送。思考过程可能占用服务的输出预算，仍需按返回原因核对推理设置。增加上下文窗口不能代替增加输出长度。官方说明：[思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)、[输出预算与结束原因](https://api-docs.deepseek.com/api/create-chat-completion/)。

新版后端按服务返回的结束原因分别提示输出预算耗尽、仅思考无正式回复、服务拒绝、工具调用或普通空正文；不会把思考过程替代为科研结论，也不会自动重发收费请求。更新后端代码后需重启分析服务才能启用该诊断。已有运行结果不受这类解读错误影响。

系统从当前已完成记录生成摘要，校验所读取产物的登记哈希。实测摘要绑定 `analysis_id`，仅包含真实对照与扰动观测的条件、实际人数、共同面板、表达/代谢变化、覆盖与警告；不会补造预测或验证指标。在线结果包含来源、表达单位合同、摘要中的前 20 行基因和代谢任务，以及可用的官方完整性总体统计。前 20 行沿用已保存报告顺序，不是完整结果或重新进行的统计筛选。

图表解读还包含当前 PCA/UMAP 方法、表达或代谢空间、选中基因/任务、方法参数、PCA 对照参考解释方差、各群体有效细胞数、均值、中位数、四分位区间、相对对照均值差，以及展示/总细胞数和方法局限。后端根据冻结来源重新读取当前统计，不接受客户端上传统计。

摘要不包含逐细胞表达矩阵、坐标、细胞 ID、图像或源文件路径。模型解释图的读法与统计量，不能声称直接观察到了点云分离、重叠或曲线形状。细胞背景和扰动目标仍属于结果摘要的一部分，发送前可展开“完整发送摘要”检查全部上下文（包括默认提示词与来源）。生成时再次核对摘要 SHA-256，内容发生变化会要求重新预览。

实测可选任务为主要结果解读、基因表达变化、代谢任务变化、覆盖与局限说明、后续科研验证建议。当前科研图解读和预测与实测比较仅对运行结果开放；不能把实测摘要当作图像或预测质量评价。快捷提问和最多 1200 字的补充问题可指定关注点。大模型输出作为独立纯文本展示，不修改原始科学结果、任务状态或数据。生成文本可能错误，不能代替原始证据、显著性检验或生物学验证；覆盖不等于准确率，scCellFie 分数不等于实测通量。收起侧栏保留当前结果；切换实测/预测来源、分析记录、图表指标、降维方法或空间后清除旧预览与解读。生成中可取消等待；已发送上游的请求可能仍产生费用。编辑问题或任务后需要重新生成。

摘要中的均值差不等于显著性或 log2 fold change。前 20 项不能回答面板之外的基因或完整通路问题；目标不在预测输出面板时只能讨论面板内响应。AI 受控协议测试不代表真实外部模型已通过科学质量评估。

解读仅保留在当前页面，可下载包含模型、时间、来源、问题、图表选择、完整摘要、摘要哈希和服务返回 token 用量的 JSON。

## 自定义与本机服务

默认允许 OpenAI、Gemini、Claude、DeepSeek 与硅基流动的上述官方 origin。其他服务由管理员在 `.env` 中登记**完整 origin**（协议、主机及端口，不带路径），重启后端后生效：

```dotenv
CELLLENS_ASSISTANT_EXTRA_ORIGINS=https://models.example.org,http://127.0.0.1:11434
CELLLENS_ASSISTANT_TIMEOUT_SECONDS=90
```

设置页面会列出当前允许范围。用户可将基础地址填写为 `http://127.0.0.1:11434/v1`；这里的本机是运行 CellLens 后端的机器。额外地址由部署者信任并管理，避免加入不受控域名或敏感内网服务。前端不能修改部署的数据库、GPU、文件路径和资源限制。

后端不跟随重定向、不读取代理环境变量、不自动重试；单进程最多同时处理 2 个模型列表/生成请求，请求体不超过 64 KiB、摘要不超过 48,000 字节、生成响应不超过 4 MiB（含服务返回的思考内容，仅展示正式正文），超时配置范围 5–90 秒。模型列表最多读取 5 页、保留 500 个模型，每页响应上限 512 KiB；只在同一允许地址分页，不访问服务返回的任意下一页 URL。错误提示不会返回上游错误正文或密钥。兼容接口不包含工具调用、自动执行或模型训练。

协议参考：[OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)、[Gemini 官方兼容接口](https://ai.google.dev/gemini-api/docs/openai)、[Claude Messages](https://platform.claude.com/docs/en/api/messages/create)。服务商的具体模型可用性、额度、数据保留和 token 参数以其文档为准。

设置流程参考 [Cherry Studio 的模型管理](https://www.cherryai.com/docs/en/mobile/model-management/)和 [Open WebUI 的兼容服务接入](https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-openai-compatible/)：命名连接、获取目录与手填模型并存，目录获取与生成测试分开。推理协议依据 [OpenAI](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)、[Gemini](https://ai.google.dev/gemini-api/docs/openai)、[Claude](https://platform.claude.com/docs/en/build-with-claude/extended-thinking)、[DeepSeek](https://api-docs.deepseek.com/guides/thinking_mode/)文档核对；具体可用性仍受账号和模型限制。

## 为什么不同实验的覆盖数字相同

官方完整性依据本次基因面板的名称和冻结代谢库计算，不使用表达量判断基因是否包含在面板中。同一面板和数据库会产生相同的覆盖数字；改变扰动、细胞数或随机种子可以改变表达与任务分数，但不会扩展模型的输出基因范围。代谢库基因覆盖表示数据库基因中有多少包含在面板中，“全部关联基因完整覆盖的任务”表示任务关联基因是否齐全，不表示任务受扰动影响或预测正确。

当前数字可用 `.venv/Scripts/python.exe -m scripts.audit_current_coverage` 对已完成在线实验重新核对；脚本检查保存产物的清单哈希、独立计算基因集合交集，并从本地冻结数据库重新计算官方完整性，只读取实验数据。
