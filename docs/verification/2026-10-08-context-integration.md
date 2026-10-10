# 三个新增背景的真实预测接入验收

日期：2026-10-08。已接入 RPE1、Jurkat、HepG2 的官方 ST-HVG fewshot 权重与对应实测对照，三次真实 GPU 运行均完成。运行模式 online，三次创建均 cache_hit=false。使用 NVIDIA GeForce RTX 4060 Laptop GPU，经 state_gpu_runner 将官方模型载入 CUDA；每次原始命令与 stdout/stderr 均保存在运行目录。

## 已完成的真实输出

| 背景 | 运行编号 | 参数：扰动 / 预测细胞数 / 种子 | 目标预测矩阵 | 预测与克隆输入的平均绝对差 | 网页 |
| --- | --- | --- | --- | ---: | --- |
| RPE1 | `run_30dc0a6410ca4e2d` | AAMP / 64 / seed 42 | 64 x 2000 | 0.370770 | [打开结果](http://127.0.0.1:8001/workbench?run=run_30dc0a6410ca4e2d) |
| Jurkat | `run_5e06e0fd0b9140a7` | AAMP / 64 / seed 42 | 64 x 2000 | 0.411373 | [打开结果](http://127.0.0.1:8001/workbench?run=run_5e06e0fd0b9140a7) |
| HepG2 | `run_1b544f2cff4d400a` | AAMP / 64 / seed 42 | 64 x 2000 | 0.334033 | [打开结果](http://127.0.0.1:8001/workbench?run=run_1b544f2cff4d400a) |

“预测与克隆输入的平均绝对差”只检查预测数值确实不同于输入，不是准确性指标。实际预测位于 predicted.h5ad 的 obsm['X_hvg']；原始 .X 是保留的输入表达，不能直接把它当作预测。原始 H5AD 含 64 个目标扰动行及 64 个 non-targeting 行，分析只使用目标扰动的 64 行。每种背景的单细胞图包含 1024 个实测对照点、64 个模型预测点、0 个实测扰动点。

每次运行均生成 gene_deltas.csv、完整代谢评分及反应产物、projection.json、task_trace.json、summary.json、manifest.json 和 report.html。141 个任务有有限变化值；覆盖计数为 supported 7、exploratory 2、insufficient 209，覆盖不足继续如实显示，不能将这些分类当作预测准确度。

## 输入与模型来源

- 官方模型仓库 arcinstitute/ST-HVG-Replogle，固定 revision bb6a9562cbbf1fd152df14cc53b4cc7517c77175，分别使用 fewshot/rpe1、fewshot/jurkat、fewshot/hepg2。每种背景的 checkpoint/config/var_dims/pert/batch/cell_type 六个文件均按官方哈希校验；source_manifest.json 保存实际 SHA-256。
- 对照来自官方 arcinstitute/State-Replogle-Filtered，固定 revision d790193bb2c93726541a75ca3fa873a92ed44da5。每种背景无放回选择 1024 个真实 non-targeting 细胞，种子 42；保留源行号、原始 barcode、批次、来源版本和未修改的源表达。
- RPE1 覆盖 56 个批次，Jurkat/HepG2 各 55 个批次。每种背景前三个来源行与原始 HDF5 读取结果逐值相同；全输入的 X_hvg 也与 .X 按官方基因顺序取列逐值相同。
- 2,000 基因面板独立从各背景官方 var_dims.pkl 提取，四背景有序列表一致。每种模型分别读取实际扰动映射，登记 2,024 个编码标签。
- 现有 K562 模型登记行与原快照相同，原对照/观测的 SHA-256 保持不变；已有运行目录未重写。

## 工程改动与检查

1. 前后端请求契约支持 K562、RPE1、Jurkat、HepG2，参数面板继续由实时 catalog 驱动。STATE 输出新增背景身份校验，防止其他背景结果被误标成目标背景。
2. 新增 prepare_context_assets.py，分模型下载、真实对照提取、登记三个阶段；大型表达只读取所选行。新增 smoke_contexts.py 完成 MySQL + CUDA + STATE + scCellFie 真实链路与数值/来源/清单检查。
3. 后端 78 项测试通过；Ruff 和 BasedPyright 通过；前端 vue-tsc/Vite 构建通过。依赖自身有弃用提示，Vite 有原有体积提示，均不影响上述验收。
4. 四背景在线 catalog 均可用；新三个背景没有观测数据和合成预计算包，validation_ready/precomputed_ready 均为 false。浏览器验证背景切换、扰动目录、三组真实表达/任务/追溯/状态图，以及 390px 页面无横向溢出；无 pageerror。
5. 三次预测的 summary/projection/genes/metabolic-tasks/reactions/report 和实际任务追溯接口均返回 200。manifest 声明的每个产物 SHA-256 均与磁盘文件相符。

另修复扰动词表大小写边界：API 统一大写，提交官方 CLI 前按实际词表恢复原始基因名称；未知或歧义标签报错，日志出现对照 one-hot 回退也报错。补充真实 RPE1/C12ORF45 运行 `run_96407dcdb4e245ad`，TSV 实际使用 `C12orf45`，得到 64 个目标预测细胞且没有对照回退；记录见 `mixed_case_run.json`。官方模型映射文件保持原始哈希。

这是背景接入与真实推理验收，尚未进行预测准确性或跨背景泛化评测。使用的是官方 fewshot 权重，未在本项目训练新模型。状态图目前为真实表达上的共享固定种子随机投影，未接入 SE/UMAP，也未人工补造坐标或预测细胞。

## 复查与重现

机器可读记录位于 reports/context-integration-2026-10-08/：real_runs.json、source_spot_checks.json、live_catalog.json、before-models.json、before-datasets.json。浏览器结果与截图位于 reports/frontend/contexts/。这些大型/运行本地文件不进入 Git。

每次输出位于 data/derived/runs/<run_id>/。启动系统后可直接从上述链接或实验记录打开；在工作台选择任一新增背景与支持列表中的扰动可创建新的真实运行。

如需从未准备的环境重建资产：

```powershell
.\.venv\Scripts\python.exe -m scripts.prepare_context_assets --phase models
.\.venv\Scripts\python.exe -m scripts.prepare_context_assets --phase controls
.\.venv\Scripts\python.exe -m scripts.prepare_context_assets --phase register
```

登记前会保存注册表快照。真实冒烟检查前先停止旧应用 worker，避免它以旧注册表领取新背景任务；随后运行 python -m scripts.smoke_contexts，再恢复应用。重复新推理需要设置新的 --seed，脚本会拒绝将缓存当作新运行。日常启动已准备的系统无需重复下载或登记。

[官方模型资产](https://huggingface.co/arcinstitute/ST-HVG-Replogle/tree/bb6a9562cbbf1fd152df14cc53b4cc7517c77175)；[官方数据资产](https://huggingface.co/datasets/arcinstitute/State-Replogle-Filtered/tree/d790193bb2c93726541a75ca3fa873a92ed44da5)。

最终网页服务运行在 http://127.0.0.1:8001。恢复原地址时，8000 被本机 verge-mihomo 的出站连接占用；使用空闲端口运行应用，没有关闭代理或修改系统网络配置。验收命令：`python scripts/check_contexts_frontend.py --url http://127.0.0.1:8001 --runs reports/context-integration-2026-10-08/real_runs.json`。

后续重新启动可使用现有入口：`powershell -ExecutionPolicy Bypass -File scripts/start_system.ps1 -ApiPort 8001 -SkipBuild`。当前八组浏览器检查均通过，无 pageerror；首页可用背景也已改为跟随实时 catalog。
