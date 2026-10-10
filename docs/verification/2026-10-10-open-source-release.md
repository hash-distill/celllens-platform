# 开源许可与 Git 发布检查

日期：2026-10-10。本记录覆盖当前源代码发布、许可归属及冻结资源的可检出性。

## 许可处理

- 根目录增加标准 MIT `LICENSE`，版权主体为 CellLens contributors，年份为 2026；Python 与前端包元数据同步声明许可。
- `NOTICE` 与 `docs/THIRD_PARTY_NOTICES.md` 说明第三方许可例外。STATE 源码及运行时修改后的上游函数仍遵循 CC BY-NC-SA 4.0；模型用途及输出继续按实际版本的模型许可处理。
- `licenses/` 保留六份上游许可文本。STATE 模型条款按 SE-600M 固定 revision 核对；scCellFie 许可保留原版权声明；HGNC 的 CC0 标准文本取自 SPDX。来源与 SHA-256 记录在 `licenses/manifest.json`。

## 源码和资源边界

旧 `models/` 忽略规则同时排除了 `configs/models/`。现在只忽略根目录 `/models/`，四种细胞背景的注册配置进入源代码仓库。权重、原始 H5AD、完整运行产物、`.env`、安装依赖和本机构建产物继续排除；`output/` 临时截图目录也排除。

`.gitattributes` 对配置、数据库、HGNC 映射、注册基因列表及许可原文关闭换行转换，保留其按字节计算的 SHA-256。资源内容与登记哈希不因发布而重算或替换。

## 验证结果

| 检查 | 结果 |
|---|---|
| 完整后端 pytest | 136 passed，6 条上游警告 |
| Ruff，backend 与 scripts 全部文件 | 通过 |
| basedpyright | 0 errors，0 warnings，0 notes |
| 前端类型检查与生产构建 | 通过；现有大 chunk 提示保留 |
| uv 锁文件一致性 | 通过；只补齐已有 report 依赖声明，没有变更依赖版本 |
| 工作文件与 Git 暂存区发布检查 | 通过；没有发现所检模式的密钥、私钥、禁止资产或超限文件 |
| 冻结资源与许可哈希 | 六份许可、七份数据库/名称映射资源及十六份注册配置/划分/基因列表全部一致 |

Git 暂存区中的实际字节已通过同一哈希清单核对，`git diff --cached --check` 通过。上游许可原有空白及冻结配置的末尾空行按原始字节保留。本地详细发布检查输出保存在忽略的 `reports/formal-system-2026-10-10/`，不进入公开仓库。正式运行浏览器和真实导出检查见 [正式操作验证记录](2026-10-10-formal-operation.md)。

以上检查证明工程检查与源文件完整性通过，不代表独立留出评价、模型泛化或实验验证已经完成。
