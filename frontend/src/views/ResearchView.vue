<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MeasuredSetup from '../components/MeasuredSetup.vue'
import ParamPanel from '../components/ParamPanel.vue'
import { useDraftStore } from '../stores/draft'
import { useRunStore } from '../stores/run'
import type { CellLine } from '../types/run'
import { isIntegerInRange } from '../utils/number'

const route = useRoute(), router = useRouter()
const draft = useDraftStore(), runs = useRunStore()
const experimentType = computed({
  get: () => route.query.type === 'prediction' ? 'prediction' : 'measured',
  set: (type: string) => {
    void router.replace({path:'/research', query:{...route.query, type, cell_line:draft.cellLine, perturbation:draft.perturbation || undefined}, hash:route.hash})
  },
})
watch(() => [route.query.cell_line, route.query.perturbation], ([cellLine, perturbation]) => {
  if (typeof cellLine === 'string' && ['K562', 'RPE1', 'Jurkat', 'HepG2'].includes(cellLine)) draft.setCellLine(cellLine as CellLine)
  if (typeof perturbation === 'string') {
    const value = perturbation.trim().toUpperCase()
    if (!value || (value.length <= 128 && /^[A-Z0-9][A-Z0-9._-]*$/.test(value))) draft.perturbation = value
  }
}, {immediate:true})
watch(() => [route.query.max_cells, route.query.seed], ([maxCells, seed]) => {
  if (typeof maxCells === 'string' && isIntegerInRange(maxCells, 1, 4096)) draft.measuredMaxCells = maxCells
  if (typeof seed === 'string' && isIntegerInRange(seed, 0, 2147483647)) {
    if (experimentType.value === 'measured') draft.measuredSeed = seed
    else draft.seed = seed
  }
}, {immediate:true})
const description = computed(() => experimentType.value === 'measured'
  ? '比较实测对照与扰动，分析表达变化及表达推断的代谢评分。'
  : '预测扰动后的表达变化；有实测数据时可进一步比较。')
</script>

<template>
  <div class="page research-page">
    <header class="page-heading"><div><span class="eyebrow">RESEARCH / EXPERIMENT SETUP</span><h1>研究分析</h1><p>选择实验类型，设置细胞背景与扰动基因，开始一次分析。</p></div><div class="btn-row"><RouterLink to="/data-catalog" class="btn">查看数据目录</RouterLink><RouterLink to="/records" class="btn">实验记录</RouterLink></div></header>
    <section class="experiment-setup" aria-label="实验设置">
      <header class="setup-heading"><div><h2>实验设置</h2><p>切换实验类型时保留细胞背景与扰动，各类型的采样参数分别保存。</p></div><div class="experiment-type-field"><label class="label" for="experiment-type">实验类型</label><select id="experiment-type" v-model="experimentType" class="select" :disabled="draft.measuredSubmitting || runs.submitting" aria-describedby="experiment-description"><option value="measured">实测分析</option><option value="prediction">模型预测</option></select></div></header>
      <p id="experiment-description" class="experiment-description" aria-live="polite"><span>{{ experimentType === 'measured' ? '实测数据' : '模型预测' }}</span>{{ description }}</p>
      <MeasuredSetup v-if="experimentType === 'measured'" />
      <ParamPanel v-else destination="detail" horizontal />
    </section>
    <footer class="research-notes"><p>结果将标明实测或预测来源，可从实验记录中继续查看与解读。</p><RouterLink to="/methods/models">了解分析方法与数据来源 →</RouterLink></footer>
  </div>
</template>

<style scoped>
.research-page{max-width:1500px;margin:0 auto}.experiment-setup{border:1px solid var(--border);background:var(--card);border-radius:var(--radius);overflow:visible}.setup-heading{padding:24px 28px;display:flex;justify-content:space-between;gap:32px;align-items:center;border-bottom:1px solid var(--border)}.setup-heading h2{font-size:18px;font-weight:500;margin:0 0 8px}.setup-heading p{font-size:12px;line-height:1.8;color:var(--muted);margin:0}.experiment-type-field{width:230px;flex-shrink:0}.experiment-type-field .label{margin:0 0 8px}.experiment-type-field select{width:100%;min-height:42px}.experiment-description{display:flex;align-items:baseline;gap:16px;margin:0;padding:12px 28px 0;color:var(--muted);font-size:12px;line-height:1.9}.experiment-description>span{white-space:nowrap;color:var(--primary);font-weight:600}.experiment-setup :deep(.param-panel>.card){border:0;margin:0;background:transparent;border-radius:0}.research-notes{display:flex;justify-content:space-between;gap:24px;margin-top:22px;font-size:12px;color:var(--muted);line-height:1.8}.research-notes p{margin:0}.research-notes a{color:var(--primary);white-space:nowrap}@media(max-width:900px){.setup-heading{align-items:flex-start;flex-direction:column;gap:18px}.experiment-type-field{width:100%}.research-notes{flex-direction:column;gap:8px}.experiment-setup :deep(.horizontal>.card){grid-template-columns:1fr}.experiment-setup :deep(.horizontal .perturbation-field){grid-column:1}.experiment-description{align-items:flex-start;flex-direction:column;gap:4px}}
</style>
