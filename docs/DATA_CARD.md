# DATA CARD

当前冻结 Replogle K562 子集，来源为 `arcinstitute/State-Replogle-Filtered/replogle_concat.h5ad`，许可记录为 Replogle et al. 2022（CC-BY-4.0）。本地 control 为 3000 个 non-targeting 细胞，heldout 为 1465 个细胞；两份 H5AD 均包含与模型注册表同序的 `obsm['X_hvg']`（2000 基因），并登记 SHA-256。

拆分单位为 perturbation，`configs/splits/replogle-v1.json` 冻结 12 个 K562 测试扰动。工程 smoke test 使用不在测试列表中的 `MYC`，没有打开冻结测试集。基因名按去空格、转大写规范化，重复或缺失注册 HVG 会直接失败。
