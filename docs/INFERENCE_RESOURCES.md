# 推理资源管理

在“连接服务”页（`/status`）按 K562、RPE1、Jurkat 或 HepG2 准备资源。页面打开只读取状态，用户勾选许可并点击后才开始准备；不会自动下载所有背景。下载发生在后端所在机器，远程浏览器不会收到模型文件。

## 下载内容与来源

每个背景的模型包约 467 MiB，包含六个文件：

```text
models/state-replogle-<background>/
├── checkpoints/final.ckpt
├── config.yaml
├── var_dims.pkl
├── pert_onehot_map.pt
├── batch_onehot_map.pkl
└── cell_type_onehot_map.pkl
```

固定来源为 `arcinstitute/ST-HVG-Replogle` revision `bb6a9562cbbf1fd152df14cc53b4cc7517c77175` 下对应 `fewshot/<background>/`。完整目标、大小与 SHA-256 位于 [`backend/app/resources/inference_assets.json`](../backend/app/resources/inference_assets.json)，与官方目录元数据和本地有效文件核对。checkpoint 通过校验仍不足以在线就绪；官方模型的五个配套文件也必须通过固定哈希检查。

模型条款以页面链接的官方固定版本与 [STATE 模型许可](https://github.com/ArcInstitute/state/blob/main/MODEL_LICENSE.md) 为准，有非商业使用限制。项目 MIT 不覆盖这些模型与输入数据。

## 真实对照准备

已有登记对照哈希有效时直接复用。缺少或无效时，从 `arcinstitute/State-Replogle-Filtered` revision `d790193bb2c93726541a75ca3fa873a92ed44da5` 的 `replogle_concat.h5ad` 读取背景、基因标签和所需表达行；不下载完整约 30 GB 图谱。

按对应背景筛选 non-targeting 对照，固定种子 42，最多抽取 1,024 个细胞。保留源表达和实际细胞条码，按已登记基因面板建立有序 HVG 槽位，不插补或生成实测数据。产物记录来源 revision、源行号与抽样参数，再核验背景、对照标签和面板。

新对照保存为 `data/raw/replogle-<background>/control-managed-<hash>.h5ad`，以新 dataset ID 登记在当前背景前面。旧 ID、旧路径和旧文件继续保留，历史实验按原身份核验；不把旧的观测诊断字段复制为新对照的验证结论。新登记用于在线推理，不证明训练排除或独立生物学验证。

源码已包含应用配置、基因面板、拆分配置与共享 scCellFie 六个数据库文件。它们不按细胞背景重复下载。诊断观测和历史实验不在本按钮下载范围内。

## 任务、取消与恢复

后台单任务执行，并通过操作系统文件锁防止同一项目多个 API 进程同时安装。状态保存于 `data/derived/resource-downloads/jobs.json`；下载中的临时文件以 `.part` 结尾。

任务依次检查已有文件、下载缺失文件、验证摘要、按需准备对照，再完成登记。权重最后发布，防止只有部分配套文件时误报可用。有效原文件跳过；错误原文件仅在新文件校验成功后留存备份并替换。大小或摘要失败的文件不会启用。

取消后保留已下载部分，重试时验证 Range 响应后续传；上游忽略 Range 时重新下载该文件。进程中断后显示可重试，完整但尚未发布的文件重新校验。对照提取在可终止的独立子进程执行；取消会停止该子进程，重试使用新的临时目录，不与上次未完成产物混用。提取进程还监测其 API 父进程是否退出。

资源完成后前端刷新背景目录，当前进程无需重启。其他端口发起的任务可查看，但取消需要回到发起任务的服务端口。正式部署仍使用单个 Web 进程；下载锁不是多实例任务部署已经完成验收的证明。

## 就绪与失败处理

- **资源就绪：**六个模型文件和登记真实对照均通过哈希检查。
- **在线就绪：**还需可用 GPU、STATE / Python 科学依赖、worker 和共享资产；以工作台背景可用状态为准。
- **推理完成：**只表示特定任务执行完成，不等于独立评价通过。

网络失败、校验失败、磁盘不足、缺少提取依赖都会给出失败状态并允许重试。下载前要求至少两份所选模型大小的空闲空间；Python 环境、对照和运行文件仍需额外空间。对照数据处理使用 model/report 依赖，页面按钮不会安装驱动或 Python 包。

API 只接受固定细胞背景和许可确认，不接受自定义 URL、目录或 revision；HTTPS 下载及其重定向限制在固定官方域，校验固定大小与哈希，并拒绝项目目录外的目标。同源浏览器限制减少跨站发起；它不提供用户身份或配额管理，公网部署应在应用前配置访问控制。

## 接口

| 方法与路径 | 行为 |
|---|---|
| `GET /api/v1/resources` | 各背景文件、对照、任务进度与固定来源；`Cache-Control: no-store` |
| `POST /api/v1/resources/{cell_line}/download` | Body 为 `{"accepted_license": true}`，202 接收任务 |
| `POST /api/v1/resources/{cell_line}/cancel` | 取消当前端口拥有的准备任务 |

非法背景、额外字段或未确认许可返回 422，来源拒绝返回 403，资源繁忙或在其他进程取消返回 409。GET 不启动下载。

实现位于 `services/resource_downloads.py`、`services/resource_control.py` 和 `api/resources.py`。验收范围见[本次验证](verification/2026-10-22-inference-resources.md)。
