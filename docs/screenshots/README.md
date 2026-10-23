# 日期明确的页面截图

以下截图来自 2026-10-10 运行中的正式构建和真实模型结果回放，用于保留该版本的展示证据。2026-10-20 已整合新主题，当前外观以 [前端整合验收](../verification/2026-10-20-frontend-theme-integration.md) 为准。

| 文件 | 内容 |
|---|---|
| [home.png](home.png) | 首页：研究流程与正式操作入口 |
| [experiment-records.png](experiment-records.png) | 服务器实验记录、筛选和分页 |
| [response-workbench.png](response-workbench.png) | 真实 ALDOA 结果回放，运行来源、表达与代谢结果 |
| [scientific-cell-state.png](scientific-cell-state.png) | 共同对照 PCA、逐细胞指标着色和累积分布 |
| [about.png](about.png) | 正式使用说明、服务状态、结果含义与适用范围 |

上述回放读取已保存的真实结果，本次未重新执行模型。图示和文件下载可追溯到同一运行；截图本身不证明预测准确性。验证记录见 [正式操作修订](../verification/2026-10-10-formal-operation.md)。

## 已移出的旧页面

旧结构示意、合成投影和早期讲解截图已从当前树移出；历史版本可从清理前提交 `9ba57c7` 恢复。旧结构示意不代表形态预测，旧合成图不能作为真实结果。

## 2026-10-22 当前构建

| 文件 | 内容与范围 |
|---|---|
| [workbench-2026-10-22.png](workbench-2026-10-22.png) | 当前构建读取已保存的 K562 / ALDOA 在线预测结果；含科研图解读入口，本次截图未重跑模型 |
| [inference-resources.png](inference-resources.png) | 实际后端读取四个背景的现有资源，均通过文件校验；不是模拟下载完成截图 |
| [measured-2026-10-22.png](measured-2026-10-22.png) | 当前构建的真实 K562 / AAAS 直接分析；未调用 STATE，匹配后 1360 对照、32 实测、6546 共同基因 |
| [catalog-2026-10-22.png](catalog-2026-10-22.png) | 固定公开源 5759 实测组合与 2333 模型支持但本源无记录组合的真实目录 |

亮暗主题及三种桌面宽度的原始截图、协议夹具交互记录保存在本地 `reports/resources-2026-10-22/`，范围见[资源验收](../verification/2026-10-22-inference-resources.md)。
