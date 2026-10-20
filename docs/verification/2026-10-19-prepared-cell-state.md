# 任务完成前准备 PCA / UMAP 科研图

日期：2026-10-19。用户要求将结果页“核对来源并生成UMAP”移到任务进度阶段。

## 当前行为

- STATE、表达与代谢分析后进入现有 `validating` 阶段，85%显示“正在准备 PCA / UMAP 科研图”。
- 在 attempt partial 目录中完成表达空间 PCA/UMAP、可用代谢空间 PCA/UMAP及默认 SVG，95%表示准备完成，再发布正式目录、登记清单，最终完成至100%。
- 图形准备期间持续续租。表达图准备失败不会标记完成；代谢缺失保留明确不可用状态，不补造数据。
- 默认页面读取已保存 JSON/SVG；其他着色指标复用保存坐标和逐细胞数据，不重新拟合PCA/UMAP。PDF/PNG仍在用户导出时渲染。
- 数据压缩保存为不含pickle对象的NPZ，图形单独附于 `run_id/cell_state/`，绑定原manifest哈希并登记准备清单；主manifest、原预测和指标不改变。
- 历史未回填结果保留兼容读取。显式回填脚本仅做CPU准备，不推理、不训练、不新增实验记录。

## 本次已有记录回填

实际准备7个已完成在线实验，共28份默认SVG及对应JSON。每项原有17个顶层文件哈希均保持一致。新附件合计55,159,700 bytes，约52.6 MiB；单项约5.3–15.5 MiB。

逐项运行、耗时、文件数与大小：`reports/prepared-cell-state-2026-10-19/backfill.json`。该耗时包括首次UMAP依赖/编译及不同规模数据，不能作为新GPU任务总耗时或生产SLA。

执行入口：

```powershell
.\.venv\Scripts\python.exe -m scripts.prepare_cell_state_figures --all-completed --report reports/prepared-cell-state-2026-10-19/backfill.json
```

也支持重复指定 `--run-id`，按运行幂等核验。禁止同时指定两种选择方式。

## 验证

- 完整回归：238 passed、6 warnings；164.31秒。之后补充的临时目录发布和LRU驱逐两项回归均通过，合计240个不同用例已验证。
- 首轮新增测试在准备服务缺失时失败；流水线测试在仍采用完成后准备时失败，再实现对应行为。
- 清空内存缓存后，禁止重建、PCA和UMAP拟合，仍可读取默认图及切换任务；SVG API在禁止renderer时仍能返回默认图。
- 运行附件篡改拒绝；原输入仍逐次核验。表达可用但代谢缺失、准备异常、幂等重复准备、原manifest绑定均有用例。
- 实际staging准备后原子改名，再登记读取成功；渲染期间清空请求LRU不影响准备。
- 代码复核提出的“耗时准备在正式目录发布后扩大中断窗口”和“依赖全局LRU驻留”已修正并复核，无新增阻塞项。原有一般任务恢复限制不在本次宣称解决的范围。
- Ruff通过；BasedPyright 118文件0错误0警告；前端类型检查和生产构建通过。已有按需Three分块体积警告仍在。

## 主服务验收

在确认活动实验为0后重启本地8000服务以加载新代码，`ready=true`（数据库、worker、GPU配置均就绪）。没有发起新的GPU推理。

重启后逐一读取7个真实记录的表达/代谢默认UMAP：JSON与已保存文档一致，SVG字节哈希与已保存图一致。JSON请求0.0675–0.1912秒，SVG请求0.1229–0.2656秒；这是本机接口时间，不是浏览器整页加载时间或网络SLA。

CUA实际浏览 `run_68521813f0ce4507`，表达UMAP显示1088细胞（1024对照、64预测），默认指标GAS5，图形和数值可见；截图 `reports/prepared-cell-state-2026-10-19/result-page.png`。

证据：同目录下 `pytest.xml`、`pytest-publication.xml`、`pyright.json`、`backfill.json`、`live-api.json`及页面截图。

本轮没有新GPU推理，因此“新任务的完成顺序”由真实流水线代码和隔离测试证明；已有真实数据的计算、持久化、重启读取及页面显示已现场验证。不将两类证据混称一次新的GPU全链运行。
