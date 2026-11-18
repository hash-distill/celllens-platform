<template>
  <div class="page about-page">
    <header class="about-heading"><span class="eyebrow">CELL LENS / GUIDE</span><h1>使用说明</h1><p>从两项分析任务开始，在四个结果视图中检查变化、来源与解释范围。</p></header>
    <section class="about-tasks" aria-label="两项分析任务">
      <article class="card"><span class="task-index">01 / 已观察的数据</span><h2>实测数据分析</h2><p>比较真实对照组与扰动组的表达响应，计算表达衍生的功能支持。</p><ul><li><strong>公开数据：</strong>先查询背景与扰动覆盖，再选择细胞上限与采样种子。</li><li><strong>自有 H5AD：</strong>直接在页面上传 H5AD，系统读取可选字段；选择对照与处理组、确认表达尺度，建立数据版本后开始分析。也提供脚本接入 API。</li></ul><RouterLink class="btn btn-primary" to="/research?type=measured">开始实测数据分析 →</RouterLink></article>
      <article class="card"><span class="task-index">02 / 模型生成的响应</span><h2>基因扰动预测</h2><p>选择模型支持的细胞背景与目标基因，设置预测细胞数和种子，获得预测表达与功能线索。</p><ul><li>输入目标必须在当前模型支持词表中，执行能力可在服务状态查看。</li><li>有匹配实测时，可查看模型与实测的诊断比较；它不等于已独立验证的泛化效果。</li></ul><RouterLink class="btn btn-primary" to="/research?type=prediction">开始基因扰动预测 →</RouterLink></article>
    </section>
    <section class="card">
      <h2>从输入到完成结果</h2>
      <ol class="guide-list">
        <li><strong>查覆盖：</strong>在<RouterLink to="/data-catalog">数据图谱</RouterLink>搜索背景与目标基因，区分固定源实测、本地核验与模型词表支持。</li>
        <li><strong>选任务并核对：</strong>进入<RouterLink to="/research">新建研究</RouterLink>，完成“选择分析任务 → 设置输入与条件 → 核对并提交”。实测分析内再选公开数据或自有 H5AD。</li>
        <li><strong>跟踪执行：</strong>离开提交页后，仍可在<RouterLink to="/records">实验记录</RouterLink>查看状态与已完成产物。失败或中断应先读提示；提交响应不确定时先核对记录，避免重复创建。</li>
        <li><strong>阅读结果：</strong>打开<RouterLink to="/records?status=completed">已完成结果</RouterLink>，先看数据身份、实际组数和可用产物，再进入下表所列视图。</li>
      </ol>
    </section>
    <section class="card">
      <h2>四个结果视图</h2>
      <div class="table-wrap"><table class="table"><thead><tr><th scope="col">视图</th><th scope="col">看什么</th><th scope="col">如何解释</th></tr></thead><tbody>
        <tr><td>研究总览</td><td>数据身份、实际细胞数、共同基因、主要表达变化与代谢覆盖。</td><td>先核对本次比较使用了哪些数据；缺失、零值和未生成产物分别显示。</td></tr>
        <tr><td>表达响应</td><td>基因表达均值及差值；可用时查看 PCA / UMAP 群体分布。</td><td>点云来自表达特征，不能解释为细胞的物理位置或形态。差值方向、群体及单位以本次图表标注为准。</td></tr>
        <tr><td>代谢任务</td><td>代谢任务、反应评分与可用成员覆盖。</td><td>scCellFie 计算表达衍生的功能支持，评分也不等于实测代谢通量、代谢物浓度或酶活性。</td></tr>
        <tr><td>实验对照</td><td>实测任务查看实测对照与扰动组；预测任务查看可用的模型与实测诊断。</td><td>两种来源分开标识；实测组间差异是描述性比较，预测与实测吻合也不自动构成独立泛化证据。</td></tr>
      </tbody></table></div>
      <p class="guide-note">公开展览可能只开放已发布的总览与导出内容；能否查看具体图表和成员明细，以该案例实际提供的产物为准。</p>
    </section>
    <section class="card">
      <h2>从任务评分回到证据</h2>
      <ol class="guide-list">
        <li>在研究总览或代谢任务中选中一个任务，沿用任务中文名、英文原名和稳定 ID 核对身份。</li>
        <li>打开“来源与证据”，查看当前任务对应的反应、已覆盖与缺失基因，以及映射版本；无法可靠匹配时会明确说明不可用。</li>
        <li>继续核对运行来源、输入和产物指纹、表达单位与解释限制；可保存带当前选择的笔记，供后续讨论。</li>
      </ol>
      <p class="guide-note">首页细胞结构图用于概念展示。研究结果页展示本次冻结表达数据的投影、表达响应与代谢任务；PCA／UMAP 坐标是表达降维坐标，不代表细胞的实际形态或空间位置。</p>
    </section>
    <section class="card">
      <h2>选择合适的导出文件</h2>
      <div class="table-wrap"><table class="table"><thead><tr><th scope="col">用途</th><th scope="col">文件</th><th scope="col">内容范围</th></tr></thead><tbody>
        <tr><td>分享阅读</td><td>阅读报告 · HTML</td><td>供浏览器查看的结果报告；需以本次可用产物为准。</td></tr>
        <tr><td>保留完整结果</td><td>完整结果与来源 · ZIP</td><td>本次可导出的结果文件及来源说明。</td></tr>
        <tr><td>继续表格分析</td><td>当前结果表 · CSV</td><td>按钮注明的结果表；原始基因和任务 ID 保持不变。</td></tr>
        <tr><td>保留研究记录</td><td>研究记录与笔记 · JSON</td><td>结果身份、来源与已保存笔记；不代替原始表达矩阵。</td></tr>
      </tbody></table></div>
    </section>
    <section class="card">
      <h2>页面工具与适用范围</h2>
      <p>桌面右侧工具栏提供 AI 科研解读、模型设置、顶部 / 底部与使用说明。窄屏页面工具收起在页尾，展开后显示文字标签。顶栏可切换亮暗主题；<RouterLink to="/status">服务状态</RouterLink>展示当前服务与执行能力。</p>
      <p>AI 科研解读在预览摘要后向已配置模型发送内容，需结合原始数据复核。自有数据、公开实测和模型预测的来源分别保留；分析完成表示产物已保存；这不代表模型的独立泛化已验证，也不构成生物学验证。</p>
      <p class="guide-note">公开目录按 K562、RPE1、Jurkat、HepG2 四种背景组织固定来源；自有数据可使用声明的独立背景。当前源无记录不等于其他研究没有测量。模型支持词表、上游划分声明与独立验证不能互相替代。</p>
    </section>
  </div>
</template>
<style scoped>
.about-page{max-width:1440px;min-width:0}.about-heading{margin:0 0 26px}.about-heading h1{font-size:32px;font-weight:500;margin:12px 0}.about-heading p{color:var(--muted);font-size:14px;line-height:1.85}.eyebrow,.task-index{font-size:12px;color:var(--primary);letter-spacing:1px}.about-page h2{font-size:21px;font-weight:500;margin:0 0 16px}.about-tasks{display:grid;grid-template-columns:1fr 1fr;gap:18px}.about-tasks .card{background:linear-gradient(135deg,var(--card-soft),var(--card));border-radius:15px;padding:26px;display:flex;flex-direction:column}.about-tasks h2{margin-top:14px}.about-tasks .btn{align-self:flex-start;margin-top:auto}.about-page p,.about-page li{font-size:14px;line-height:1.9}.about-page ul{padding-left:20px;color:var(--muted);margin:0 0 24px}.about-page> .card{border-radius:15px;padding:26px;margin-top:20px}.about-page p{margin:10px 0}.guide-list{padding-left:22px;display:flex;flex-direction:column;gap:10px;margin:0}.guide-list a,.about-page p a{color:var(--primary)}.about-page .guide-note{font-size:13px;line-height:1.85;color:var(--muted);margin-top:17px}.table-wrap{overflow:auto}.table{min-width:620px}.table th{font-size:13px}.table td{font-size:14px;line-height:1.8;vertical-align:top}.table td:first-child{white-space:nowrap;color:var(--primary);font-weight:500}@media(max-width:700px){.about-tasks{grid-template-columns:1fr;gap:0}.about-tasks .card,.about-page>.card{padding:22px}.about-heading h1{font-size:28px}}
</style>
