# scCellFie 官方完整性接入与验收

日期：2026-10-09。

## 实现与方法

直接调用已安装的 scCellFie 0.6.2 公共 Python 接口 `sccellfie.reports.compute_dataset_completeness`，采用 `metric="fraction_zeroed"`、`threshold=1.0`。接口见 [官方报告 API](https://sccellfie.readthedocs.io/en/latest/api/index.html#reports)。不调用外部云推理服务。

输入为本次真实预测 `gene_deltas.csv` 的完整基因面板，以及原始冻结数据库全部 GPR 和 task-by-reaction 矩阵。先过滤数据库会掩盖缺失基因，因此完整性计算使用未裁剪的数据库。AnnData 只有基因名和零行，不构造表达数据；该官方接口衡量数据集的基因可用范围，不读取单细胞表达量。

官方输出包含数据集汇总、218 项任务和 787 项反应的全部关联基因/单基因必需项覆盖、影响加权完整性及缺失基因。连续指标直接序列化，不重新设置 80%/60% 阈值。新真实运行自动生成 `official_completeness.json`，旧真实运行通过独立补充脚本登记该报告。

`GET /api/v1/runs/{run_id}/completeness` 验证报告登记哈希、运行编号及原预测面板文件哈希。接口不在读取时重算。任务结果返回 `completeness_available`，前端据此请求报告；没有报告的旧演示不会主动发送一个必然 404 的请求。

## 真实运行与实际结果

四个背景的下列 AAMP 运行均为已有真实模型预测，未重写预测结果：

| 背景 | 运行编号 |
|---|---|
| K562 | `run_4d0b3038ea8642af` |
| RPE1 | `run_30dc0a6410ca4e2d` |
| Jurkat | `run_5e06e0fd0b9140a7` |
| HepG2 | `run_1b544f2cff4d400a` |

共补齐 7 个真实运行的官方报告；4 个缺少冻结任务追溯的历史运行跳过，不推断其数据库身份。补充过程逐文件核验原有文件 SHA-256 保持不变，并单独登记新增报告，保留旧预测、任务分数、摘要和运行清单。

当前四背景都使用相同 2000 基因输出面板，因此数据集完整性相同；不同模型权重与细胞输入产生的预测数值仍然不同。

| 官方指标 | 实际值 |
|---|---|
| 代谢库基因覆盖 | 131 / 931，14.0709% |
| 全部关联基因完整覆盖的任务 | 7 / 218 |
| 全部关联基因完整覆盖的反应 | 86 / 787 |
| 任务平均影响加权完整性（all） | 0.38710648716456453 |
| 任务平均基因覆盖比例（all） | 0.17545306609781952 |

影响加权完整性 38.7% 不是预测准确率。192 项任务的单基因必需集合为空，官方对此返回 1；页面显示“无单基因必需项”，不将其解释为完整证据。官方 essential 统计中的 199 项完整覆盖包含这 192 项，因此不能据此声称 199 项任务可靠。均一参考下的单基因消融也不等于实验必需性，多个替代基因共同缺失的效应不能从单基因影响之和直接得到。

响应页和代谢页优先展示官方连续指标、可搜索的全部任务表、缺失基因详情及完整 JSON 下载。原项目三档保留在历史兼容结果与比较摘要中，并明确标为项目旧规则、非官方置信度。真实有报告的结果页移除旧分类筛选。

代谢评分不再被项目 80%/60% 阈值提前阻止；仍拒绝空基因输入，使用原冻结阈值和官方评分管线。允许生成分数不等于补足缺失基因，评分必须结合完整性报告阅读。

## 检查与证据

- 官方接口结果一致性、AND/OR GPR、空必需集合、重复规范基因、旧阈值不阻止评分、报告及来源哈希篡改拒绝、未来运行产物生成均有后端检查。
- 7 个已补齐报告的真实 API 均返回 200，包含 218 项任务和 787 项反应，证据：`reports/official-completeness/api-checks.json`。
- 四背景各自的响应页/代谢页共 8 组检查，加完整 JSON 下载和旧演示兼容，共 10 组浏览器检查通过；无页面错误、无失败响应。检查包括旧筛选隐藏、缺失基因、匹配/空搜索、运行身份、全部报告行和手机宽度。证据：`reports/frontend/official-completeness/checks.json` 及同目录截图、下载。
- 原代谢交互回归另有 7 项检查通过。证据：`reports/frontend/metabolism-fix/`。
- 最终完整后端回归：82 passed，6 项第三方依赖警告，42.55 秒。前端类型检查和生产构建通过；Ruff 通过，BasedPyright 0 errors / 0 warnings，`git diff --check` 通过。
- 一次完整回归在 Windows 临时目录原子重命名处遇到 `WinError 5`；相同的两项参数化测试在新临时目录复查通过。没有为此改变生产管线或关闭系统保护。

补充报告的原文件哈希证据保存在 `reports/official-completeness/backfill.json`。这些运行证据和截图保留在本机 `reports/`，不纳入 Git。

## 复核命令

从仓库根目录执行，后端已运行于本机端口 8001：

```powershell
.venv\Scripts\python.exe -m scripts.backfill_official_completeness
.venv\Scripts\python.exe -m pytest backend/tests -q --basetemp reports/official-completeness/pytest-final
.venv\Scripts\python.exe -m ruff check backend scripts
.venv\Scripts\python.exe -m basedpyright
python scripts/check_completeness_frontend.py --url http://127.0.0.1:8001
```

浏览器检查使用安装了 Playwright/Chromium 的 Python。重复补充脚本核验已有报告后跳过，不覆盖原报告；该命令会更新本机补充审计 JSON。

## 当前边界

本次验证使用已有真实预测，没有为了完整性分析再运行一批 GPU 预测；新运行产物接入通过后端运行链路测试验证。本次没有证明跨背景预测泛化能力，也没有增加模型输出基因数。提高低覆盖需采用具有更完整、正确训练输出空间的模型或新增训练，并对新增输出进行真实预测和验证。SE 嵌入投影只改善表达空间展示，不提供缺失基因的代谢证据。
