# 第三方许可与引用

更新日期：2026-10-10。项目自有代码与文档采用根目录 [MIT 协议](../LICENSE)。[NOTICE](../NOTICE) 列出许可例外；本文件区分软件、模型、数据库、输入数据及模型结果的归属。

## 许可范围

MIT 适用于 CellLens 原创 API、分析适配器、前端、脚本和文档。它不替代安装依赖、上游源代码及其运行时修改版本、模型权重、外部数据与数据库、模型生成结果的许可。文档中的真实结果截图保留其模型来源与适用的输出条款。

| 内容 | 来源与许可 | 本仓库处理 |
|---|---|---|
| STATE / arc-state 0.11.1 源代码 | [官方代码许可](https://github.com/ArcInstitute/state/blob/main/LICENSE)，CC BY-NC-SA 4.0；本机发行包完整原文见 [许可副本](../licenses/state/CC-BY-NC-SA-4.0.txt) | 通过依赖安装，不将上游源代码改授 MIT。SE 适配器按指纹核验并在运行时修改上游推理函数，修改后的函数继续遵循上游代码许可 |
| STATE 权重、模型使用与输出 | [模型许可](https://github.com/ArcInstitute/state/blob/main/MODEL_LICENSE.md) 与 [可接受使用政策](https://github.com/ArcInstitute/state/blob/main/MODEL_ACCEPTABLE_USE_POLICY.md)；固定 SE 来源的原文及哈希见 [副本目录](../licenses/state/README.md) | 不提交权重；模型用途、输出引用及再分发按完整上游条款处理，不能凭本项目 MIT 推断完整系统可自由商用 |
| scCellFie 0.6.2 与冻结 human Recon2 数据库 | [官方 MIT 许可](https://github.com/earmingol/scCellFie/blob/main/LICENSE.txt)，Copyright (c) 2024, Wellcome Sanger Institute；[原文副本](../licenses/scCellFie-0.6.2-MIT.txt) | 六个数据库文件及其 SHA-256 清单保留在 `data/registry/sccellfie/human/`，保留原作者与数据库来源；数据库所引用的其他资源仍按其条款使用 |
| HGNC 名称映射 | [HGNC 官方数据许可](https://www.genenames.org/about/license/)，CC0 1.0 | `data/registry/gene_identity/` 保留下载来源、源文件哈希和映射策略；HGNC 数据不改授 MIT |
| Replogle K562 输入数据 | 注册表记录 Replogle et al. 2022，CC-BY-4.0；来源见 [模型与数据](MODEL_AND_DATA.md) | 不提交原始 H5AD；记录不能替代原始数据条款 |
| RPE1 / Jurkat / HepG2 输入数据 | 固定 State-Replogle-Filtered 来源；对应原始 Replogle/Nadig 数据各自条款 | 不提交原始 H5AD，不将所有背景统称为 Replogle 2022 数据 |
| Python 与前端依赖 | `pyproject.toml` / `uv.lock`、`frontend/package.json` / `package-lock.json` 记录版本；各发行包许可证为准 | 不提交安装目录；重新打包依赖或前端构建产物时保留所需第三方许可 |

仓库不分发 `.env`、本机权重、原始 H5AD、完整运行产物、安装依赖或临时输出。MIT 许可声明只授予本项目有权授予的部分，不覆盖第三方商标和单独受限的资产。

## 方法引用

- STATE：Adduri, A. et al. (2025). [Predicting cellular responses to perturbation across diverse contexts with State](https://doi.org/10.1101/2025.06.26.661135)。使用 STATE 源码、参数或结果时保留上游要求的引用。
- scCellFie：[Atlas-scale metabolic activities inferred from single-cell and spatial transcriptomics](https://doi.org/10.1101/2025.05.09.653038) (2025)。其他 CellFie、Recon2 相关来源见 [官方项目引用](https://github.com/earmingol/scCellFie#how-to-cite)。
- HGNC：HUGO Gene Nomenclature Committee，[Genenames.org](https://www.genenames.org/)，RRID:SCR_002827；数据提供方建议保留来源归属。

## 许可副本来源

`licenses/manifest.json` 记录每份副本的来源、版本或固定 revision 和 SHA-256。STATE 代码许可从本机 `arc-state==0.11.1` 发行包复制；模型条款从已核验的 `arcinstitute/SE-600M` revision `5a9a80f44f7ce32ce57059933ef0d735d7c10ce5` 复制；scCellFie 许可从本机 `sccellfie==0.6.2` 发行包复制，并与官方仓库原文核对一致。

重新分发上游模型、修改后的模型代码、数据或依赖时，应同时检查该实际版本的完整许可证及通知，保留本文件不能代替那些要求。
