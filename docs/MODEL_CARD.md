# MODEL CARD

当前启用 `state-replogle-k562-fewshot-v1`（STATE/arc-state 0.11.1），checkpoint、配置和 2000 基因 HVG 面板均登记 SHA-256。模型支持 2024 个扰动，真实 `MYC` smoke test 已在 RTX 4060 Laptop GPU 上通过，模型设备为 `cuda:0`。许可为 Arc State Model Non-Commercial License；因此该模型只用于竞赛演示和非商业研究。RPE1 checkpoint 尚未核验，注册表保持禁用。

在线输出经过 H5AD 可读性、有限值、扰动标签、预测面板宽度、基因存在性和 provenance 校验。当前 smoke test 证明工程可运行，不等同于完整生物学泛化结论；最终测试扰动仍需按冻结拆分独立报告。
