# 真实扰动观测与预测比较验收

日期：2026-10-15。

## 数据与实际运行

固定来源：`arcinstitute/State-Replogle-Filtered` revision `d790193bb2c93726541a75ca3fa873a92ed44da5` 的 `replogle_concat.h5ad`。HDF5 范围读取保留原表达、源行号、条形码、背景、扰动和 `gem_group`。

在读取效果前，按已有真实 `expression-cp10k-v2` 预测冻结 15 个背景/扰动组合，最多 256 个细胞、种子 42、不放回选取。实际 8 组合有测量，均不足上限，所以保存全部 627 个真实细胞；其余 7 组合记录为 0。选择清单为 `reports/measured-comparison-2026-10-15/selection.json`，catalog 为 `data/registry/observations.json`。

| 背景 / 扰动 | 固定源真实测量数 |
|---|---:|
| HepG2 / ALDOA | 96 |
| Jurkat / AAMP | 39 |
| Jurkat / AASDHPPT | 97 |
| Jurkat / ABHD11 | 97 |
| Jurkat / ALDOA | 75 |
| K562 / AAMP | 76 |
| K562 / ALDOA | 77 |
| RPE1 / ALDOA | 70 |

无测量的组合为 HepG2/AAMP、HepG2/ACD、K562/ASCC3、K562/MYC、RPE1/AAMP、RPE1/AQR、RPE1/C12ORF45。零仅适用于该固定 filtered 版本。

原数据库两个实验不变：Jurkat/ABHD11 新增独立比较；RPE1/AQR 说明无观测。通过当前 8000 正式 API 另建四背景 ALDOA 在线预测，`n_cells=256`、`seed=43`，全部 `cache_hit=false`，实际 GPU 推理和评分完成。没有恢复用户已清理的历史数据库记录；额外历史文件的比较不冒称新推理。

| 背景 / 扰动 | 运行 | 共有批次后对照/预测/实测 | 变化 Pearson | MSE / 不变化 MSE |
|---|---|---:|---:|---:|
| K562 / ALDOA | `run_47d09620968f48cf` | 2086 / 187 / 76 | 0.437600 | 0.798352 |
| RPE1 / ALDOA | `run_aef55809479e4c21` | 720 / 175 / 67 | 0.894370 | 0.208534 |
| Jurkat / ALDOA | `run_34737097754841fd` | 817 / 209 / 72 | 0.497999 | 0.861288 |
| HepG2 / ALDOA | `run_41504106326f404d` | 840 / 209 / 96 | 0.262609 | 1.552911 |
| Jurkat / ABHD11 | `run_469edf3453324f66` | 657 / 52 / 76 | 0.140252 | 1.830720 |

后两例没有优于不变化基线，完整保留，不按效果筛除。相关性不能称为准确率百分比。

## 指标与来源验证

评价使用完整 2000 个对齐基因及合法零变化，计算统一 `mean(log1p(CP10K))` 群体差值。STATE 预测读取真正保存预测的 `X_hvg`，不误用仍保留输入表达的 `.X`；明确排除模型附带的模拟对照。共有批次原频率保留，不根据效果调权重。

`scripts/verify_measured_comparisons.py` 从实际控制、预测、观测 H5AD 重建群体，核对全部成对基因均值、细胞身份和原运行输出哈希，再直接调用官方 Cell-Eval 0.8.2 的 `mse_delta`、`mae_delta`、`pearson_delta`。五个当前案例全部一致；证据 `reports/measured-comparison-2026-10-15/official-verification.json`。只核对选定表达指标，未执行完整官方 profile。

DE 沿用 Scanpy Wilcoxon、BH-FDR < 0.05、tie correction；页面给出项目 Overlap@N/AP 的具体排序和分母定义。数量误差命名为 `deg_count_absolute_error`。无有效代谢比较时 MAE、方向一致率和 Top-K 返回 null。

## 产物与生命周期

- 新 API：`GET /api/v1/runs/{run_id}/comparison`、`/comparison/download?table=json|genes|tasks`。
- 比较独立保存于 `data/derived/comparisons/{run_id}/`，自有清单绑定原预测清单、真实表达输入和输出哈希，不改写原预测及摘要。
- 后续准备核对原表达槽、尺度、配置/检查点/面板声明及原表达合同，拒绝同 ID 下改变解释方式；观测尺度必须明确匹配合同。
- 比较准备状态先于模型完成状态登记，页面可自动重试读取。失败尝试使用 UUID 独立目录保留，重试无需删除旧证据；成功以不可覆盖目录发布。
- API、下载及助手均核验来源，发生变化时拒绝使用；助手只接收比较摘要，不自动调用外部服务。

本批实际数值对应源码指纹 `7f76f219c27125b6c883a8fefc949b6a09b1ac44b09634070a32d53fb6b6e3fe`，快照在 `reports/measured-comparison-2026-10-15/executed-code/`。后续解释/状态加固没有重写该批结果。

## 工程与页面验收

- 完整后端：**245 passed，9 warnings，212.08 秒**；无失败或跳过。JUnit：`reports/measured-comparison-2026-10-15/pytest-reviewed.xml`。
- 前端类型检查和生产构建通过；Ruff 全项目检查通过。
- 新增比较、来源、助手上下文等相关文件 BasedPyright 为 0 errors / 0 warnings。全项目另有两处既有可空值错误：`backend/app/api/experiments.py:87`、`scripts/check_pagination_status_frontend.py:17`，未把局部通过称为全项目通过。
- 当前主服务 8000 六个数据库实验均完成浏览器验收：五个有比较、一个无观测。基因/任务切换、搜索、三组数值、优于/差于基线提示、完整 CSV / JSON、实测快捷项和助手上下文核对通过。
- 1500/768/390px 无页面横向溢出，页面脚本错误为 0。截图、下载和验收 JSON 在 `reports/measured-comparison-2026-10-15/browser/`。
- 独立只读代码复核提出的三项来源解释/生命周期问题已修正并复核通过。主服务已加载最终后端与前端，没有重复推理 worker；本次没有调用真实外部辅助大模型。

## 复查

```powershell
.venv\Scripts\python.exe -u -m scripts.prepare_measured_comparisons evaluate
.venv\Scripts\python.exe -u -m scripts.verify_measured_comparisons
python scripts/check_measured_comparison_frontend.py --url http://127.0.0.1:8000
.venv\Scripts\python.exe -m pytest backend/tests -q
```

已有成功比较校验后读取；失败尝试保留，新尝试独立生成。`extract` 拒绝覆盖现有 catalog；扩充来源应冻结新的选择清单和版本，不根据指标好坏替换观测。

科学边界仍为 `held_out_validation=false`、检查点训练排除未核实。它们是有来源的匹配实测诊断，不能直接宣称独立泛化、真实通量或因果验证。操作说明见 [实测对比指南](../guide/MEASURED_COMPARISON.md)。
