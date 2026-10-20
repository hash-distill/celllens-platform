<template>
  <section class="response-intro" aria-label="扰动响应分析流程">
    <div class="intro-copy"><span class="micro">CELLLENS / PERTURBATION INTELLIGENCE</span><h2>一次扰动，<br />看见细胞状态与功能变化。</h2><p>比较单细胞表达状态的前后分布，定位基因与代谢响应，再沿知识库关联追溯依据。把一次计算，变成可检查的实验线索。</p><span class="intro-caption">从顶部进入实验记录选择已有实验，或在实验工作台创建实验。</span></div>
    <div class="method-flow">
      <div class="method-step"><span class="step-index">01</span><div><small>STATE</small><h3>预测单细胞状态</h3><p>对照细胞集合 + 基因扰动 → 预测表达分布</p></div><span class="step-symbol">Δ</span></div>
      <div class="method-step"><span class="step-index">02</span><div><small>scCellFie</small><h3>解析代谢功能</h3><p>表达支持 → 反应分数 → 任务分数</p></div><span class="step-symbol">↗</span></div>
      <div class="method-step"><span class="step-index">03</span><div><small>CELLLENS</small><h3>追溯分析依据</h3><p>关联基因 · 数据覆盖 · 运行来源</p></div><span class="step-symbol">◎</span></div>
      <p class="flow-caption">分析流程示意 · 选择运行后显示实际数值</p>
    </div>
  </section>
</template>
<style scoped>
.response-intro{display:grid;grid-template-columns:1fr 1fr;gap:36px;align-items:center;min-height:490px;padding:40px;background:var(--card);border:1px solid var(--border);position:relative;overflow:hidden}.intro-copy{position:relative}.intro-copy>.micro{color:var(--primary);font-size:10px;letter-spacing:.13em}.intro-copy h2{font-size:clamp(26px,2.4vw,38px);font-weight:500;line-height:1.5;letter-spacing:-.03em;margin:24px 0}.intro-copy p{font-size:13px;line-height:2;color:var(--muted);max-width:390px}.intro-caption{display:block;font-size:11px;margin-top:32px;color:var(--primary)}.method-flow{border-left:1px solid var(--border-strong);padding-left:28px}.method-step{position:relative;display:flex;align-items:center;gap:18px;padding:25px 0;border-bottom:1px solid var(--border)}.step-index{font:italic 26px Georgia,serif;color:var(--panel-index)}.method-step small{font-size:10px;letter-spacing:.14em;color:var(--primary)}.method-step h3{font-size:18px;font-weight:500;margin:6px 0}.method-step p{font-size:11px;color:var(--muted);margin:0}.step-symbol{margin-left:auto;font:34px Georgia,serif;color:var(--panel-index)}.flow-caption{font-size:10px;color:var(--muted);margin-top:18px}@media(max-width:1050px){.response-intro{padding:25px;gap:25px;grid-template-columns:1fr}.method-flow{border-left:0;padding:0}.method-step{padding:18px 0}.intro-copy h2{font-size:28px;margin:18px 0}.intro-caption{margin-top:20px}}
</style>
