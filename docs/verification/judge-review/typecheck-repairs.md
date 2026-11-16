# 类型检查修复

全项目 basedpyright 初次检查发现 110 项错误，集中在国赛重构的七个文件。逐项处理后全项目为 0 errors、0 warnings、0 notes；没有通过添加 Any、忽略指令或更改检查配置规避问题。

| 文件 | 处理 |
|---|---|
| access.py | 明确异步响应体与普通响应体分支，保留公开 JSON 脱敏 |
| api/research.py | 显式默认值；检查导出结果、来源与指纹，异常返回受控错误 |
| core/storage.py | SQL 写操作结果精确收窄为 CursorResult，运行语义不变 |
| controlled_import.py | 明确 HDF Group/Dataset、稀疏/稠密矩阵与列类型；拒绝命名类型、null Dataset、缺失矩阵及异常列 |
| measured_results.py | 校验覆盖列，异常分类列保留不可用，不臆造分类 |
| research_projection.py | 仅对已知数量求和，未知总数保留 None |
| worker.py | 显式启动参数，保持 Windows 隐藏窗口与 Linux 独立会话 |

独立修复代理完成 68 项相关回归，最后调整后追加 29 项导入/排序检查；三种异常 HDF 隔离样例均明确拒绝。主代理重新执行完整套件、Ruff 和全项目 basedpyright，并重启 API/CPU/GPU worker。

重启后重新读取三条新真实记录的结果、JSON 导出和 PCA，共 9 个接口检查通过；科研助手本地上下文可读。真实验收 H5AD 预检通过且原文件未改变，138 个旧产物哈希及 1 条既有研究笔记保留。详见 final-runtime.json 和 backend-tests.xml。

本次没有改变科学算法、归一化定义、冻结来源或历史结果。
