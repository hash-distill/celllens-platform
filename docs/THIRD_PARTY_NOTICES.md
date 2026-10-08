# 第三方说明

代码、模型权重与数据的许可分别管理。发布或提交时保留对应上游许可与引用，不将第三方限制改写为项目自有许可。

| 资产 | 当前记录 |
|---|---|
| STATE / arc-state 0.11.1 | 代码、权重及可接受使用政策以各自上游文件为准；模型注册表记录 Arc State Model Non-Commercial License |
| scCellFie 0.6.2 | 原项目许可记录为 MIT；交付其代码或数据库时保留对应许可与论文引用 |
| Replogle K562 | 注册表记录 Replogle et al. 2022 (CC-BY-4.0)，来源见 [模型与数据](MODEL_AND_DATA.md) |
| RPE1 / Jurkat / HepG2 | 固定官方 State-Replogle-Filtered 来源；分别核对原始 Replogle/Nadig 数据及其许可，不将全部背景统称为 Replogle 2022 数据 |
| 其他 Python 依赖 | 版本由 pyproject.toml 和 uv.lock 管理，许可遵循各依赖发行文件 |

仓库默认不分发本机权重、原始 H5AD 或真实运行产物。注册表标签是项目记录，不能替代上游完整许可；重新打包第三方资产时核对原始文件。
