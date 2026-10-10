# 2026-10-04 工程检查记录

保留以下历史结果用于追溯，不作为当前环境自动就绪或生物学准确性的证明。

- [checks.json](checks.json)：真实 API、三维交互、结果与页面检查。
- [production-checks.json](production-checks.json)：后端同源页面直达、刷新与结果加载检查。
- [页面截图](../../screenshots/README.md)：精选的实际页面。

这些检查覆盖工程行为。原自动播放检查主要验证切章与暂停，没有验证连续生理动画；当前自动播放为章节计时器。细胞器关联、形态预测及正式泛化评价不能从这些记录推断。

当前脚本分别为 `scripts/check_3d_frontend.py` 和 `scripts/check_production_frontend.py`。新结果写入 `reports/frontend/`，不会覆盖本目录中的历史记录。
