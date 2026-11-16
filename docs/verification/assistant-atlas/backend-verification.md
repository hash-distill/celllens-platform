# 助手后端验证

验证目录：`D:\全球校园人工智能精英大赛\celllens-national`。

## 测试结果

执行命令：

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_assistant_conversation.py backend/tests/test_assistant.py backend/tests/test_assistant_connections.py backend/tests/test_assistant_measured.py backend/tests/test_assistant_figures.py -q
```

结果：`129 passed, 2 warnings in 41.76s`。其中新增对话测试 15 项，其余为已有助手测试。两条警告来自 Starlette 对测试客户端及 AnyIO 别名的弃用提示。

新增测试覆盖旧请求兼容、6 轮对话顺序、两种服务协议、证据摘要单次注入、历史来源不匹配、当前摘要变化、字段与总字节限制，以及历史内容计入输入预算。所有模型服务请求使用 `httpx.MockTransport`。本次未调用真实模型服务，未验证真实模型的回答质量。

Ruff 检查通过；`backend/app/assistant.py` 的 BasedPyright 检查为 0 错误、0 警告；本次修改文件的 `git diff --check` 通过。

## 接口变更

`POST /assistant/interpret` 新增两个可选字段。未提供历史时，保持原有单次请求行为。

| 字段 | 类型与约束 |
| --- | --- |
| `history` | 已完成轮次的数组，默认 `[]`，最多 6 轮 |
| `history[].question` | 字符串，最多 1200 个字符，允许空字符串以支持预设问题 |
| `history[].purpose` | 与当前 `purpose` 相同的枚举，默认 `interpret` |
| `history[].answer` | 非空白字符串，长度为 1 至 16,000 个字符 |
| `history_context_sha256` | 64 位小写十六进制字符串；历史非空时必须提供 |

历史数组按紧凑 JSON 编码，UTF-8 总长度上限为 64,000 字节。后端拒绝超限历史，不截断内容。已有中间件继续限制整个 POST 请求最多 65,536 字节；客户端需要为连接设置、当前问题及其他字段预留空间。

后端先重新构建并验证当前证据摘要。当前摘要哈希变化时返回 `409 CONTEXT_CHANGED`。历史哈希与当前摘要不一致时返回 `409 HISTORY_CONTEXT_CHANGED`。缺少历史哈希或违反结构约束时返回 `422`。

`GET /assistant/capabilities` 新增 `conversation_history: true`，并通过 `conversation_limits` 返回轮数、问题字符数、回答字符数及历史字节数上限。

前端接口在原参数末尾新增 `history`（默认 `[]`）和可选的 `historyContextSha256`，已有调用方式保持兼容。调用顺序如下：

```typescript
interface AssistantHistoryTurn {
  question: string
  purpose?: Purpose
  answer: string
}

assistantApi.interpret(
  context, purpose, connection, signal, question,
  history, historyContextSha256,
)
```

## 证据边界

后端将已完成轮次构造成交替的用户消息和助手消息，并在第一条用户消息中附上本次已验证的摘要。系统提示要求重新核对证据，明确历史助手回复属于未经验证的推测。输入预算包含完整历史内容。

历史哈希用于防止客户端误将旧证据的对话带入新摘要。客户端自行提供历史和哈希，因此哈希不证明历史真实，也不提供身份认证。恶意客户端仍可提交与当前哈希绑定的任意历史；模型只能将这些内容作为对话背景，不能据此新增科研事实。

## 覆盖目录首次加载

API 重启后，覆盖目录首次请求曾等待超过 45 秒，随后日志记录 `GET /api/v1/coverage` 返回 `200 OK`。现有日志未记录请求耗时，无法给出精确冷启动时间。

代码检查显示，目录缓存指纹包含全部后端 Python 源码。助手代码变化会触发缓存重建。重建过程包含 scCellFie 导入、冻结数据库校验与解析、官方完整性计算和分类补充。服务错误日志仅出现科学依赖的文档警告，没有本次目录请求的异常栈。上述证据与首次重建耗时一致，尚未按阶段单独计时。

缓存文件 `data/derived/catalog-cache/1eb8a8bfa7ccde5b02fc21420249994af18c69cea87a76b7caf8ff81992086da.json` 的写入时间为 2026-11-16 00:16:53（本机时间）。缓存生成后执行：

```powershell
curl.exe --silent --output NUL --max-time 20 --write-out 'http=%{http_code} time=%{time_total}s bytes=%{size_download}' http://127.0.0.1:8028/api/v1/coverage
```

实测结果：`http=200 time=0.640827s bytes=1266561`。页面随后正常显示目录。此次排查未修改缓存失效范围，也未重启服务。部署更新后可提前请求覆盖目录，使首次重建在交付前完成。
