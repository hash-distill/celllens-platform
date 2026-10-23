# 首页动画与展示资源性能验收

日期：2026-10-21。基线前端来自 `ce28ff5`；本次保留页面布局、文案、轻微浮动与滚动进入效果，优化首页的渲染和展示资源。原始采样、截图与优化前构建备份位于 Git 忽略目录 `reports/home-animation-2026-10-21/`。

## 原因与验证方式

首页首屏只有健康、就绪和细胞背景目录三个 API 请求，该次基线的 `transferSize` 合计 1,774 字节，未加载实验矩阵或完整结果。持续卡顿主要来自移动光晕与多层 `backdrop-filter`、`filter: blur()` 的叠加；资源方面还使用了用于 29px 页头显示的 1254×1254 图标，以及体积较大的 PNG 展示图。

对相同页面临时关闭背景模糊后，带追踪采样的滚动帧率由约 17 提升至 52；再关闭滤镜约为 56。追踪本身会增加开销，因此该数据只用于定位，不能与未开启追踪的结果混用。优化前后的正式帧率比较均关闭追踪，使用同一 Chromium 148.0.7778.96、全新上下文、1440×1000、正常动画偏好。静止动画采样 2 秒，滚动采样 3 秒。

上一轮启动检查启用了减少动画偏好，证明的是首屏加载与资源延迟加载，未证明正常动画流畅度。本轮补齐这一检查范围。

## 修改

- 首页半透明卡片保留颜色与边框，取消对移动背景的实时模糊采样。光晕由渐变直接形成柔和边缘，不依赖实时模糊；动画只改变 transform。
- 首屏进入视口且文档可见时才运行动画；离开视口或隐藏标签页时暂停。减少动画偏好下关闭动画并释放主动图层提示。
- 滚动状态更新通过 requestAnimationFrame 合并；组件卸载时断开观察器、移除监听并取消待执行帧。一次性滚动进入效果触发后停止观察对应节点。
- 保留全部原始 PNG，生成独立 WebP 展示副本与 96px 图标。页头与 favicon 使用同一经过构建哈希命名的小图标。原 `/favicon.png` 与 `/favicon.ico` 兼容路由保留。
- 新增可重复执行的资源预算与动画生命周期检查；已有首屏、主题检查同时识别 PNG/WebP。

## 实测结果

以下是同一机器的有限采样，属于浏览器 requestAnimationFrame 间隔观察，不是所有硬件的帧率保证，也不是显示器实际呈现帧的直接计数。

| 指标 | 优化前 | 更新后的正式服务 |
|---|---:|---:|
| 浅色首屏动画 | 29.26 fps | 60.00 fps |
| 深色首屏动画 | 30.98 fps | 60.00 fps |
| 浅色滚动 | 29.34 fps | 60.00 fps |
| 深色滚动 | 29.34 fps | 60.00 fps |
| 浅色滚动帧间隔 P95 | 50.10 ms | 16.80 ms |
| 深色滚动帧间隔 P95 | 50.10 ms | 16.70 ms |
| 首屏图片传输量（含浏览器报告的响应开销） | 1,110,633 字节 | 30,551 字节 |
| 六份展示资源文件总量（不计原图备份） | 9,659,667 字节 | 413,449 字节 |

优化后两主题采样中超过 50ms 的帧数均为 0。正式服务另一次减少动画偏好的首屏检查记录 FCP 288ms、networkidle 0.788 秒；这不是完整模型服务启动耗时，不用于比较正常动画帧率。

证据：`before.json`、`*-trace.json` 为定位采样；`untraced-before.json` 与 `primary/metrics.json` 为无追踪比较；`primary-loading.json` 为首屏资源检查。`primary/hero-light.png` 与 `primary/hero-dark.png` 为更新后的实际页面。原图与生成副本的尺寸、编码参数及 SHA-256 见 `frontend/src/assets/optimized/manifest.json`。

## 可重复检查

在仓库根目录、已安装依赖且生产服务运行的条件下执行：

```bash
uv run --no-sync python scripts/optimize_frontend_images.py --check
python scripts/check_homepage_performance.py --url http://127.0.0.1:8000 --output reports/homepage-performance
python scripts/check_startup_frontend.py --url http://127.0.0.1:8000 --output reports/homepage-performance/loading.json
```

浏览器检查脚本使用安装了 Playwright 与 Chromium 的 Python 环境。可替换 URL 和报告目录，不依赖开发机器路径。首屏图片编码体积预算为 160,000 字节；同时检查正常动画、视口与文档隐藏后的暂停、恢复、减少动画偏好、路由卸载/重入、八处延迟图片和只读请求。文档隐藏场景通过浏览器内受控 visibilitychange 探针验证，未测试所有操作系统的最小化行为。

帧率只记录，不设跨硬件固定门槛。回归时在相同浏览器、窗口和动画偏好下比较；不要将带追踪、CPU 限速或减少动画的结果混在一起。

原图发生合法更新后，用 `uv run --no-sync python scripts/optimize_frontend_images.py` 重新生成，再运行 `--check` 和前端构建；该脚本不覆盖原图。WebP 为 quality=82 的有损展示编码，保留原始尺寸；96px 图标只供 UI 和 favicon 使用，不用于替代原始品牌文件。

## 验证范围

- 最终生产构建（含 TypeScript 检查）、Ruff、BasedPyright、构建指纹回归与 Git 差异空白检查通过。
- 主题与页面兼容检查在预览构建上完成 60 组桌面页面/窗口/主题组合，含历史结果和设置；实际资源可解码，主题持久化与系统同步通过，页面错误和 POST 均为 0。最终光晕边缘与减少动画资源处理调整在正式服务上重新验证。
- 正式服务的两主题正常动画、暂停/恢复、路由清理、八处图片、减少动画与首屏预算全部通过。健康与就绪接口均返回 200。
- 服务静态路由与来源相关集成测试 6 项通过；本轮没有重跑后端全量测试或提交新科学实验。既有科学算法、权重、注册表和科学数据没有修改。本轮不宣称解决覆盖页首次计算或其他科学视图的所有耗时。

渲染优化依据：[高性能动画](https://web.dev/articles/animations-guide)、[简化绘制复杂度](https://web.dev/articles/simplify-paint-complexity-and-reduce-paint-areas)、[视口与页面可见性](https://developer.mozilla.org/en-US/docs/Web/API/Intersection_Observer_API/Timing_element_visibility)。实际效果以上述采样和功能检查为准。
