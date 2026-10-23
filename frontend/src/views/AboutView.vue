<template>
  <div class="page about-page">
    <div class="card">
      <h1 class="page-title">使用说明</h1>
      <p class="muted">细胞知镜面向单基因扰动研究，优先分析公开实测数据；需要探索性推断或评估模型时，再明确选择模型预测。实测分析与预测分别保存。</p>
      <ol class="guide-list">
        <li><strong>先查数据：</strong>在<RouterLink to="/data-catalog">数据目录</RouterLink>按 K562、RPE1、Jurkat 或 HepG2 和目标基因核对固定源实测覆盖、本地数据与模型支持范围。</li>
        <li><strong>分析实测：</strong>在<RouterLink to="/measured">实测分析</RouterLink>明确启动比较，查看实际细胞数、共同基因、表达均值差、PCA／UMAP 及可用代谢评分。可取消运行、打开历史结果或导出完整 CSV、ZIP 与 HTML 报告；这一路径无需模型权重或 GPU。</li>
        <li><strong>选择预测：</strong>在<RouterLink to="/workbench">模型预测</RouterLink>从支持词表选择扰动基因，设置 64–4,096 个预测细胞及随机种子后点击“运行模型预测”。有实测时可先直接分析，也可明确运行预测，再查看结果中的实测对比。预测实验保存在<RouterLink to="/records?category=predicted">预测记录</RouterLink>，相同参数可复用已有计算结果。</li>
        <li><strong>结果解读：</strong>从顶栏<RouterLink to="/records?view=results">结果解读</RouterLink>选择已完成的实测分析或模型预测。表达状态分布通过共同 PCA／UMAP 比较扰动前后群体，提供基因与任务着色和累积分布；基因响应展示群体平均表达差；代谢功能展示任务、反应、相关基因与 GPR 规则。</li>
        <li><strong>查看数据：</strong>查看模型、数据来源、基因覆盖与实测对比。将实验加入比较，或导出科研图、数据及分析报告；结果页先展示关键表达与覆盖优先的任务对比，再按需展开专业投影和证据。实测与预测记录合并在“实验记录”表格，通过类别和状态筛选；点击“结果解读”查看已完成结果。</li>
        <li><strong>页面工具：</strong>通过顶栏右侧按钮切换亮暗主题；右侧快捷栏提供直达顶部、直达底部和使用说明。</li>
        <li><strong>服务环境：</strong>点击顶部连接状态进入<RouterLink to="/status">服务状态</RouterLink>，查看数据库、GPU、CPU、内存、磁盘与分析服务配置。</li>
        <li><strong>处理运行问题：</strong>读取页面提示，必要时重新连接或重试对应结果。“复制诊断信息”可保存运行编号、参数与错误信息，便于排查。</li>
      </ol>
    </div>

    <div class="card">
      <h2 class="card-title">结果含义</h2>
      <div class="table-wrap"><table class="table">
        <thead><tr><th scope="col">结果</th><th scope="col">解读方法</th></tr></thead>
        <tbody>
          <tr><td>表达状态分布</td><td>PCA 以对照为参考，UMAP 对本次各群体联合降维；对照、预测及可用实测共用特征坐标。每个点表示一个细胞的表达特征；图中点云不表示细胞形态、细胞器结构或物理位置。</td></tr>
          <tr><td>表达变化</td><td>实测分析为实测扰动均值减实测对照均值；模型结果另列预测均值与预测差值。表达单位为 mean(log1p(CP10K))。两类来源分别标识。</td></tr>
          <tr><td>代谢任务与反应分数</td><td>scCellFie 根据基因表达与知识库推断功能支持分数。即使输入是真实测量的 RNA，评分也不等于实测代谢通量、代谢物浓度或酶活性。</td></tr>
          <tr><td>数据完整性</td><td>展示模型预测基因对代谢任务和反应的覆盖及缺失基因。可查看各任务对应的可用和缺失基因。</td></tr>
          <tr><td>功能关联图</td><td>读取本次保存的任务—反应—基因知识关联。选择任务、反应或基因，逐层查看相关表达和分数。</td></tr>
          <tr><td>AI 科研解读</td><td>点击图旁“解读此图”或右侧栏 AI 解读，预览统计摘要后发送给已配置模型。可提问图表读法与数据变化，生成内容需结合原始数据核对。</td></tr>
          <tr><td>分析完成</td><td>本次结果已保存，可继续查看或导出；这不代表模型的独立泛化已验证。</td></tr>
        </tbody>
      </table></div>
    </div>

    <div class="card">
      <h2 class="card-title">适用范围</h2>
      <p>系统按 K562、RPE1、Jurkat、HepG2 四种背景组织 Replogle CRISPRi 数据。具体实测组合以固定源目录为准，预测范围以模型词表为准。当前源未收录某组合不等于全球没有测量；上游声明的测试划分、模型支持词表与独立验证泛化也不能相互替代。</p>
      <p class="muted small">可将最多四个实验加入比较，集中查看参数、表达响应与代谢结果。</p>
    </div>
  </div>
</template>

<style scoped>
.about-page { max-width: 1360px; }
.page-title { font-size: 21px; margin-bottom: 10px; }
.guide-list { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 8px; }
</style>
