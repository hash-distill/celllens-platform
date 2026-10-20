# 基因功能分类与双语代谢任务介绍

日期：2026-10-11。

## 页面变化

覆盖页仅展示目前覆盖的数量和清单，移除数据库分母、覆盖百分比、未覆盖清单和全库任务数。已覆盖基因支持功能类别筛选、符号/英文名称/HGNC ID 搜索，默认每页 20 条；CSV/JSON 下载也仅包含当前覆盖项。当前四背景均展示 138 个代谢基因、7 项完整覆盖任务和 86 个完整覆盖反应。

实验工作台的扰动选择器和代谢基因目录采用同一套分类。每个类别提供中英文名称及介绍，基因详情展示已登记的功能类别。多功能基因允许多个类别；不同类别人数不能相加作为总数。没有分类注释的基因明确归为“暂无分类注释”，仍可作为模型登记的扰动目标选择。

七项任务提供中英文名称、生物学说明、当前关联基因、解读范围和 UniProt 链接。说明对应 TPI1、FUT8、ME2、HMGCR、TXNRD1、CAT、DHFR。果糖相关任务保留冻结数据库原始名称，同时说明当前映射的是 TPI1 的丙糖磷酸互变，避免将其解释为完整果糖降解通路。ME2 说明使用线粒体 NAD 依赖反应，CAT 说明保留氧气产物。

## 分类依据和冻结来源

采用 [PANTHER 人类序列功能分类](https://data.pantherdb.org/ftp/sequence_classifications/current_release/PANTHER_Sequence_Classification_files/PTHR19.0_human)的显式 HGNC ID，并按 [Protein Class 层级](https://data.pantherdb.org/PANTHER19.0/ontology/Protein_Class_19.0)归到功能类别。代谢物转化酶保留氧化还原酶、转移酶、水解酶、裂合酶、异构酶和连接酶等子类。快照为 PANTHER 19.0，文件内 Protein Class 版本为 17.0；不将此版本称为最新在线注释。

[HGNC 完整集](https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt)提供批准符号、英文名称与旧名/别名。批准符号优先，旧名与别名只在身份唯一时使用；代谢数据库已有 HGNC ID 时按 ID 对齐。基因名称相似不作为功能推断依据。

生成脚本 `scripts/prepare_gene_annotations.py` 保留来源 URL、SHA-256、分类规则和压缩注释哈希，拒绝覆盖已有快照。运行时仅读取本地 `data/registry/gene_annotations/`，不逐页联网查询。快照损坏时拒绝将其用于分类；扰动 API 保留原可用目标并提示分类不可用。没有修改预测、分析产物、原始 HGNC 身份文件或模型基因面板。

## 验证

### 四个细胞背景的双语介绍

补充 K562、RPE1、Jurkat、HepG2 的细胞系名称、来源、悬浮/贴壁生长方式、生物学特点和研究用途。实验台提供随选择更新的简洁卡片，特点与用途可展开；覆盖范围页提供当前背景完整卡片和四背景对照。复用同一份介绍数据，背景可选范围与模型仍由现有登记接口决定。

介绍依据 [K-562](https://www.cellosaurus.org/CVCL_0004)、[hTERT-RPE1](https://www.cellosaurus.org/CVCL_4388)、[Jurkat](https://www.cellosaurus.org/CVCL_0065)、[Hep-G2](https://www.cellosaurus.org/CVCL_0027) 的 Cellosaurus 条目及对应 ATCC 产品资料核对，日期为 2026-10-11。RPE1 的纤毛研究用途也核对了 [ADAMTS9/20 原始研究](https://www.nature.com/articles/s41467-019-08520-7)。HepG2 采用后续研究修正后的肝母细胞瘤来源；Jurkat 的 ATCC E6-1 链接明确标注为亚克隆资料，不据此认定平台实验使用 E6-1。

本次前端类型检查、生产构建和扩展浏览器验收通过。浏览器验证四个背景的选择联动、中英文段落、Cellosaurus 来源链接、展开介绍、390/768 像素布局及深色页面，并保留原有基因分类、任务说明、覆盖数量、下载和分页回归检查。实验记录数量未改变，未提交新实验。新增截图为 `reports/gene-education-2026-10-11/four-bilingual-cell-backgrounds.png`；验收 JSON 增加对应检查项。

### 原有覆盖与分类验证

浏览器检查真实四背景和保存来源，核对页面没有数据库总数、双语类别筛选、目标可选范围、七项任务的两种语言说明、来源链接、只含覆盖项的 CSV/JSON、分页、深色及移动布局，并确认实验记录数量保持不变。验收产物：`reports/gene-education-2026-10-11/acceptance.json`。

后端测试共 15 项通过，覆盖 HGNC ID 对齐、常见基因的冻结类别、多标签计数、未知功能不猜测、缓存仍检查文件哈希、扰动分类失效时不删除可用目标、七项任务的双语说明；原覆盖来源、缓存和官方统计测试继续保留。Ruff、basedpyright、前端类型检查、生产构建和差异空白检查通过。

分类是知识库注释，任务介绍是生物学背景说明；两者都不构成当前扰动实验中的因果结论、通量测量或模型准确率证明。
