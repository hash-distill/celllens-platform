<script setup lang="ts">
import MethodDiagram from '../components/MethodDiagram.vue'
import MethodsPageHeader from '../components/MethodsPageHeader.vue'
</script>

<template>
  <div class="model-methods">
    <MethodsPageHeader eyebrow="EXPRESSION → FUNCTION" title="模型与方法" description="先预测表达，再理解功能：STATE 预测扰动后的表达，scCellFie 分析这份表达对代谢任务的支持。" />
    <article class="method-section" aria-labelledby="state-heading">
      <header><div class="method-name"><span class="method-index">01</span><div><span class="eyebrow">PERTURBATION RESPONSE</span><h2 id="state-heading">STATE <small>扰动表达预测</small></h2></div></div><span class="method-version">arc-state 0.11.1 · ST-HVG</span></header>
      <p class="method-lead">STATE 是 Arc Institute 提出的细胞扰动响应模型。State Transition（ST）利用细胞集合之间的关系学习扰动效应；State Embedding（SE）则用于学习细胞状态表示。CellLens 使用 ST-HVG 模型，在基因表达空间生成细胞扰动预测。</p>
      <dl class="method-facts"><div><dt>输入</dt><dd>当前细胞背景的对照表达、目标单基因扰动、预测细胞数与随机种子。</dd></div><div><dt>输出</dt><dd>包含 2,000 个基因的预测表达矩阵。</dd></div><div><dt>系统中的作用</dt><dd>生成预测表达，用于基因响应、扰动前后表达状态分布比较及后续代谢任务分析。</dd></div></dl>
      <p class="method-data-note">真实对照来自公开单细胞 RNA 测量；预测采样数决定模型生成的记录数，与真实对照数量分别确定。<RouterLink :to="{path:'/methods/backgrounds',hash:'#control-sampling'}">查看对照来源与采样说明 →</RouterLink></p>
      <MethodDiagram kind="state" />
      <footer><a href="https://github.com/ArcInstitute/state" target="_blank" rel="noopener">STATE 官方项目 ↗</a><a href="https://doi.org/10.1101/2025.06.26.661135" target="_blank" rel="noopener">方法论文 ↗</a></footer>
    </article>
    <article class="method-section" aria-labelledby="sccellfie-heading">
      <header><div class="method-name"><span class="method-index">02</span><div><span class="eyebrow">METABOLIC FUNCTION</span><h2 id="sccellfie-heading">scCellFie <small>代谢功能推断</small></h2></div></div><span class="method-version">scCellFie 0.6.2 · human Recon2</span></header>
      <p class="method-lead">scCellFie 将单细胞表达与代谢知识库连接，通过基因、反应和任务之间的关联计算功能分数。“代谢任务”是一项具体的生化功能，例如完成某种物质的合成或转化，可用于了解细胞的代谢功能。</p>
      <dl class="method-facts"><div><dt>输入</dt><dd>表达矩阵、基因表达阈值与 human Recon2 代谢任务知识库。</dd></div><div><dt>输出</dt><dd>反应分数、代谢任务分数及输入基因对这些功能的覆盖信息。</dd></div><div><dt>系统中的作用</dt><dd>按相同规则分析对照、预测和可用观测，比较表达对功能的支持变化。</dd></div></dl>
      <MethodDiagram kind="sccellfie" />
      <footer><a href="https://sccellfie.readthedocs.io/en/latest/" target="_blank" rel="noopener">scCellFie 官方说明 ↗</a><a href="https://doi.org/10.1101/2025.05.09.653038" target="_blank" rel="noopener">方法论文 ↗</a></footer>
    </article>
    <section class="method-bridge"><div><span class="eyebrow">IN CELLLENS</span><h2>连接表达变化与代谢功能</h2><p>从单基因扰动出发，依次查看预测表达、代谢任务和关联反应；有匹配实测时，可进一步比较预测与实测的表达变化。</p></div><RouterLink to="/methods/coverage" class="btn">了解覆盖范围 <span aria-hidden="true">→</span></RouterLink></section>
  </div>
</template>

<style scoped>
.method-data-note{font-size:13px;line-height:1.9;color:var(--muted);margin:20px 0 0}.method-data-note a{color:var(--primary);margin-left:6px}
.methods-intro{max-width:850px;margin:12px 0 42px}.methods-intro h2{font-size:32px;letter-spacing:-.04em;font-weight:500;margin:16px 0}.methods-intro p,.method-lead,.method-bridge p{font-size:14px;color:var(--muted);line-height:1.95}.method-section{border-top:1px solid var(--border-strong);padding:30px 0 38px}.method-section>header{display:flex;justify-content:space-between;align-items:center;gap:24px}.method-name{display:flex;align-items:center;gap:22px}.method-index{font:42px Georgia,serif;color:var(--border-strong)}.method-name h2{font-size:30px;letter-spacing:-.03em;font-weight:500;margin:10px 0}.method-name h2 small{font:14px var(--font);color:var(--muted);margin-left:15px;letter-spacing:0}.method-version{font:11px Consolas,monospace;color:var(--primary);padding:8px 12px;border:1px solid var(--border);border-radius:20px}.method-lead{max-width:1080px;margin:20px 0 26px}.method-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:28px;margin:0}.method-facts>div{border-left:2px solid var(--border-strong);padding-left:18px}.method-facts dt{font-size:12px;color:var(--primary);margin-bottom:10px}.method-facts dd{margin:0;font-size:12px;line-height:1.9;color:var(--muted)}.method-section footer{display:flex;flex-wrap:wrap;gap:12px 24px;margin-top:20px;font-size:11px}.method-section footer p{flex:1 1 650px;color:var(--muted);margin:0;line-height:1.8}.method-section footer a{white-space:nowrap}.method-bridge{display:flex;align-items:center;justify-content:space-between;gap:40px;padding:28px;background:var(--surface-soft);border:1px solid var(--border);border-radius:8px}.method-bridge h2{font-size:22px;font-weight:500;margin:14px 0}.method-bridge p{font-size:12px;max-width:820px;margin:0}.method-bridge>.btn{flex:none;gap:20px}
</style>
