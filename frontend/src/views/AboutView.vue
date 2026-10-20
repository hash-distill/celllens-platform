<template>
  <div class="page about-page">
    <div class="card">
      <h1 class="page-title">使用说明</h1>
      <p class="muted">细胞知镜面向单基因扰动研究，将表达预测、代谢任务分析和运行来源整合在同一实验中。</p>
      <ol class="guide-list">
        <li><strong>设置实验：</strong>选择 K562、RPE1、Jurkat 或 HepG2，再从当前背景的在线支持列表选择一个扰动基因。可设置 64–4,096 个预测细胞及随机种子。</li>
        <li><strong>运行实验：</strong>点击“开始实验”，查看运行阶段与进度。页面刷新后可继续查看同一实验，完成的实验保存在“实验记录”。相同参数可复用已有计算结果。</li>
        <li><strong>分析结果：</strong>单细胞状态提供共同对照 PCA、基因与任务着色和累积分布；基因响应展示群体平均表达差；代谢功能展示任务、反应、相关基因与 GPR 规则。</li>
        <li><strong>核对来源：</strong>查看模型与数据版本、表达尺度、数据完整性和匹配观测。将实验加入比较，或导出科研图、数据及分析报告；“结果解读”直接展示所选实验的响应概览、单细胞状态、基因与代谢结果。</li>
        <li><strong>辅助解读：</strong>在右上角“设置”选择 OpenAI、Gemini、Claude 等提供商，填写模型和 API Key。打开已完成实验，点击右下角“AI 解读”悬浮框，预览摘要后手动生成解读。生成文本供科研参考，需核对原始结果；密钥仅保存在当前标签页，可随时清除。</li>
        <li><strong>页面工具：</strong>右侧快捷栏可切换亮暗、直达顶部或底部；设置中可选择跟随系统外观。</li>
        <li><strong>服务环境：</strong>点击顶部连接状态进入<RouterLink to="/status">服务状态</RouterLink>，查看数据库、GPU、CPU、内存、磁盘与分析服务配置。</li>
        <li><strong>处理运行问题：</strong>读取页面提示，必要时重新连接或重试对应结果。“复制诊断信息”可保存运行编号、参数与错误信息，便于排查。</li>
      </ol>
    </div>

    <div class="card">
      <h2 class="card-title">结果含义</h2>
      <div class="table-wrap"><table class="table">
        <thead><tr><th scope="col">结果</th><th scope="col">解读方法</th></tr></thead>
        <tbody>
          <tr><td>单细胞状态</td><td>PCA 基于本次对照拟合，对照、预测及可用观测共用坐标。每个点表示表达状态，坐标不表示物理位置或同一细胞的前后轨迹。</td></tr>
          <tr><td>表达变化</td><td>统一 log1p(CP10K) 尺度上的预测平均表达减对照平均表达。差值排序不等于差异表达显著性检验。</td></tr>
          <tr><td>代谢任务与反应分数</td><td>scCellFie 根据表达和冻结代谢数据库计算的功能支持分数；分数变化不直接表示实测通量、物质浓度或 ATP 产量。</td></tr>
          <tr><td>数据完整性</td><td>展示模型预测基因对代谢任务和反应的覆盖及缺失基因。完整性衡量输入信息范围，不能解释为预测准确率。</td></tr>
          <tr><td>功能关联图</td><td>读取本次保存的任务—反应—基因知识关联。布局用于比较，连线不表示模型已证明的因果贡献。</td></tr>
          <tr><td>分析完成</td><td>本次计算与结果保存已完成。预测结论仍需结合数据完整性、匹配观测和后续实验判断。</td></tr>
          <tr><td>大模型辅助解读</td><td>由外部模型根据已保存摘要生成的文字，可解释结果和建议验证工作；它不是原始分析证据或生物学验证，不改动计算结果。</td></tr>
        </tbody>
      </table></div>
    </div>

    <div class="card">
      <h2 class="card-title">适用范围</h2>
      <p>系统支持四种已登记细胞背景中的单基因扰动分析。在线目标以支持列表为准；已有结果从实验记录打开。当前 Replogle 数据主要为 CRISPRi 扰动，系统不提供敲除、过表达或剂量的独立设置。</p>
      <p class="muted small">实验比较最多保存四个候选，候选列表保存在当前浏览器。系统目前用于受控科研环境，支持已登记背景的单基因扰动预测；尚不提供多基因联合扰动或在线训练。</p>
    </div>
  </div>
</template>

<style scoped>
.about-page { max-width: 1360px; }
.page-title { font-size: 21px; margin-bottom: 10px; }
.guide-list { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 8px; }
</style>
