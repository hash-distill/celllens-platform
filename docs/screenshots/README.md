# 页面截图

当前页面截图使用下列固定文件名，供 README 和交付说明引用。截图来自本地运行的桌面页面，只证明对应界面的展示状态；数值和任务结果以具体记录及[验收文件](../verification/national-refactor/)为准。

本轮截图于独立评审修复后的本地构建重新采集。交互与尺寸记录见[浏览器验收](../verification/judge-review/browser-acceptance.json)。

## 当前界面

| 文件 | 内容与解释范围 |
|---|---|
| [home.jpg](home.jpg) | 研究概览与研究入口。首页视觉为概念示意，不是模型生成的细胞影像 |
| [research.jpg](research.jpg) | 研究工作台的两项任务与输入选择。设置页面不代表已提交或已完成新分析 |
| [result.jpg](result.jpg) | K562 / ALDOA 公开实测结果的研究总览，包含结构导航与 PCA 区域；记录为 `measured_00c6134fec4544efb1ad3b6d` |
| [catalog.jpg](catalog.jpg) | 数据图谱中的来源、背景、目标与覆盖关系；不是人体解剖或真实细胞空间图谱 |
| [comparison.jpg](comparison.jpg) | 本次 Jurkat / ALDOA 新 GPU 推演的实验对照诊断；记录为 `run_feb6ebf11ef747ab`，诊断不等于独立科学验证 |
| [task-evidence.jpg](task-evidence.jpg) | 公开实测 N-连接糖基化的 6/6 成员覆盖、任务评分和关联反应入口 |
| [backgrounds.jpg](backgrounds.jpg) | 修复左右内边距后的 K562 背景与来源说明 |
| [home-mobile.jpg](home-mobile.jpg)、[comparison-mobile.jpg](comparison-mobile.jpg) | 浏览器 390 像素宽度下的首页、对照页，非手机实机测试 |

保存截图时应保留来源标签、可用性和解释边界，避开令牌、私人路径和未授权备注。结果页截图不单独证明模型准确性、独立泛化或生物学因果关系。桌面浏览器验收不等于移动设备实机验收。

## 历史界面

旧文件继续保留其原名称，仅用于回溯对应版本，不代表当前导航或功能边界。

| 文件组 | 历史内容 |
|---|---|
| `home-2026-10-23.png`、`research-2026-10-23.png`、`results-2026-10-23.png`、`catalog-2026-10-23.png` | 当时的首页、设置、HepG2 / ALDOA 历史结果和目录；结果截图读取 `run_41504106326f404d`，当次未重新运行模型 |
| `workbench-2026-10-22.png`、`inference-resources.png`、`measured-2026-10-22.png`、`catalog-2026-10-22.png` | 当时的预测回放、资源状态、K562 / AAAS 实测和覆盖目录；范围见[资源验收](../verification/2026-10-22-inference-resources.md) |
| `home.png`、`experiment-records.png`、`response-workbench.png`、`scientific-cell-state.png`、`about.png` | 早期真实结果回放与页面；范围见[正式操作修订](../verification/2026-10-10-formal-operation.md) |

更早的合成投影和讲解图不作为当前真实结果证据。当前结果投影只读取经核验的已有派生产物；结构示意不代表细胞形态预测。
