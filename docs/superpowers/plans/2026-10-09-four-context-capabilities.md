# 四背景能力补齐 Implementation Plan

**Goal:** 四背景接通在线预测、冻结真实结果演示和受名单约束的实测诊断。

**Architecture:** 增加冻结诊断协议和回放来源契约；沿用现有推理/分析/数据库链。展示读取明确来源类型，保留全部旧资产。

**Tech Stack:** FastAPI/Pydantic、MySQL、STATE/scCellFie、AnnData、Vue/Pinia。

- [x] 在 backend/tests/test_context_capabilities.py 添加失败测试：未登记诊断拒绝创建；有效协议目录；篡改协议失效；冻结回放来源检查、重绑定及旧合成兼容。
- [x] backend/app/core/diagnostic_protocol.py 集中验证协议版本、背景、观测哈希、扰动名单及 diagnostic_only 状态。registry 增加协议路径/哈希；catalog 与 POST 共用门槛，pipeline 再核验并记录协议哈希。
- [x] core/precomputed.py 验证真实冻结包原 manifest/输出哈希；schemas 增加 result_kind，api/runs.py 回放重绑定 JSON 运行号、产物全登记、历史列表来源标记。
- [x] frontend/types/run.ts 与 utils/source.ts 实现统一真实回放/合成区分；更新 ParamPanel 和所有结果页来源及观测标签。实测诊断仅展示后端批准名单。
- [x] scripts/complete_context_capabilities.py 冻结基线、字节一致拷贝 ALDOA 实测、生成协议及登记；执行四个 STATE 真实诊断，保存运行和指标；从完成运行建立真实预计算包。
- [x] pytest、Ruff、BasedPyright、typecheck/build；通过实际 MySQL 接口运行四个回放，核对原/新产物数值及哈希。
- [x] 实际浏览器验证四背景模式切换、诊断名单、来源标签、回放观测和移动端。写入 docs/verification/2026-10-09-four-context-capabilities.md，复核所有原文件。

执行命令以仓库根目录 `.venv/Scripts/python.exe -m ...` 和 frontend 下 `npm run typecheck`/`npm run build` 为准。未请求提交或推送；工作区存在其他改动，仅修改上述契约及直接使用它的视图。
