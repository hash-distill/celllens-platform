# Reactome v98 人类通路基因集

本目录只含公共知识资源，不含研究表达矩阵或用户数据。固定来源为
[Reactome v98 原始 GMT 压缩包](https://download.reactome.org/98/ReactomePathways.gmt.zip)，
发布日 2026-10-21，下载日 2026-11-16。原始压缩包保留字节，不改写 GMT。
manifest.json 保存压缩包和解压 GMT 的 SHA-256、路径、版本、来源、许可与规模。

Reactome 官方[数据许可](https://reactome.org/license)为
[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/)。
此处为数据，不含采用其他许可的插画、品牌图形或软件。
资料来源：Reactome Pathway Database, release 98；
[下载说明](https://reactome.org/download-data)、[发布记录](https://reactome.org/about/news)。

GMT 有 2,874 个 R-HSA 人类通路条目及 12,021 个不同成员符号。
人类感染通路可能包含病原体符号；这些符号不能据此认定为人类基因。
分析只接收研究中真实测得、可比较且与 GMT 完全匹配的符号。
匹配区分大小写，不猜测别名，不自动转换 Ensembl ID。
运行时完全离线，每次读取均检查两个资源摘要。

仓库根目录重新准备：

```powershell
.\.venv\Scripts\python.exe scripts/prepare_reactome.py
```

脚本固定版本 URL 和预期下载摘要；上游内容发生变化会拒绝写入。
可用 `--archive <本地原始zip>` 验证并复用下载文件。
正常分析无需下载。发布源码或离线部署时应同时保留 manifest 和 ZIP。

分析实现：`backend/app/services/pathway_analysis.py`。
背景 U 为 QC 后可检测、有效可比较、成功匹配成员符号的交集。
在 U 中分别按正向和负向均值差排序，候选数上限为 `floor(0.05 * len(U))`。
相同差值按符号排序；不纳入零差、反向候选或重复符号；U 少于 20 时没有候选。
只测试与 U 相交后有 5–500 个成员的通路，两方向所有有效测试共同 BH 校正，
包括零命中通路；无候选方向不产生测试。
低于 20% 的映射覆盖率显示 `low_coverage` 警告，此为可记录配置，不是统计显著性阈值。

输出 JSON 含完整背景、选集、比较值、所有测试、过滤通路、输入排除原因与摘要；
返回的表含全部测试，成员符号以分号分隔。FDR 仅解释候选的通路富集，
不能解释为处理效应的显著性、正式差异表达证据或因果机制验证。
此处规则是本项目的探索配置，不声称复刻 Reactome 在线服务默认设置。

验证：

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_pathway_analysis.py -q
```

测试使用人工受控计数与单侧 Fisher 精确检验、组合数公式对照，
并检查全测试集 BH、零值、背景、方向、尺寸边界、重复稳定性和资源篡改拒绝。
这些测试不是生物学验证。
