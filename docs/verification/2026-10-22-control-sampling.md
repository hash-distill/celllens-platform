# 2026-10-22 对照来源与预测采样说明

补充“方法数据 → 细胞背景”的对照来源、non-targeting 标签含义、固定抽样与数量表，并从模型方法、工作台参数增加入口。白底样式保持。工作台将参数名明确为“预测采样细胞数”，提示不会改变真实对照人数；预测数量和随机种子仍保持对齐。

页面当前人数从新增的 control_cell_count / control_metadata_verified 读取：对照文件哈希有效，obs 的细胞背景与 non-targeting 标签一致时才显示人数；仅读取 obs，不加载表达矩阵或权重。异常时保持未知。验证得到 K562 3000、RPE1/Jurkat/HepG2 各 1024。历史实验继续使用各自冻结群体，当前目录人数不覆盖历史记录。

核对当前安装 arc-state 0.11.1 的 `_cli/_tx/_infer.py`：TSV 虚拟扰动构造与模型预测基线均调用 replace=True 的取样；CellLens 将 n_cells 传入 TSV num_cells 和 --max-cells。源码 SHA-256 为 dffe0684e93dbacbb1b6ad1c29325da215ba78a46eeb424e87b916990cd2262a。官方[当前实现](https://github.com/ArcInstitute/state/blob/main/src/state/_cli/_tx/_infer.py)具有相同的有放回语义。64–4096 是本平台允许的请求范围，3000 是 K562 本地提取上限；它们不是同一个参数。预测条数可超过对照池大小，不增加独立实测/生物学重复，也不保证准确性增加。本次没有执行 4096 个细胞的 GPU 推理或新增实验。

验证证据位于 `reports/control-sampling-2026-10-22/`：

- 先观察缺少计数字段的两个回归失败，修复后方法数据、模式、运行接口共 13 项后端测试通过。计数夹具没有 X 数据集，验证只读 obs；来源哈希改变、扰动标签错误均返回未知。
- 前端 typecheck、生产 build、Ruff 与触及文件 diff 检查通过；构建保留既有大 chunk 提示。
- `python scripts/check_control_sampling_frontend.py` 通过 8 项检查：四背景实际人数、来源与有放回说明、白底及亮暗主题、参数与对齐/定位、模型方法入口，以及未知人数受控响应。无页面异常，无实验提交。
- 锚点临近页尾，滚动受页面边界限制；实际验证说明区完整可见，不要求不足空间时仍强行顶到 100px。
- 827 个原运行文件哈希与 6 条历史实验响应保持一致。
