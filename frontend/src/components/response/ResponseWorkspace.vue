<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRunStore } from '../../stores/run'
import { fmtDelta, fmtNumber } from '../../utils/format'
import TaskTrace from './TaskTrace.vue'
import CellStateTab from '../tabs/CellStateTab.vue'
import { isSyntheticResult } from '../../utils/source'
import { hasPredictionChange } from '../../utils/predictionEvidence'

const props = withDefaults(defineProps<{ runId: string; focus?: 'all' | 'genes' | 'tasks' }>(), { focus: 'all' })
const runs = useRunStore()
const entry = computed(() => runs.entry(props.runId))
const synthetic = computed(() => isSyntheticResult(entry.value?.record?.request.mode, props.runId, entry.value?.record?.result_kind))
const selectedGene = ref('')
const selectedTask = ref('')
const projectionOpen = ref(props.focus !== 'tasks')
const evidenceFilter = ref('all')
const hasOfficial = computed(() => entry.value?.tasks.data?.completeness_available === true)
function completenessLabel(fraction: number) {
  return fraction >= 1 ? '关联基因齐全' : '存在缺失关联基因'
}
const genes = computed(() => (entry.value?.genes.data?.items ?? []).filter(hasPredictionChange).slice().sort((a,b) => Math.abs(b.predicted_delta!) - Math.abs(a.predicted_delta!)))
const tasks = computed(() => (entry.value?.tasks.data?.items ?? []).filter(t => hasPredictionChange(t) && (hasOfficial.value || evidenceFilter.value === 'all' || t.evidence_level === evidenceFilter.value)).slice().sort((a,b) => Math.abs(b.predicted_delta) - Math.abs(a.predicted_delta)))
const geneRows = computed(() => genes.value.slice(0, 8))
const taskRows = computed(() => tasks.value.slice(0, 8))
const gene = computed(() => genes.value.find(g => g.gene === selectedGene.value))
const task = computed(() => tasks.value.find(t => t.id === selectedTask.value))
const maxGene = computed(() => Math.max(1e-9, ...geneRows.value.map(g => Math.abs(g.predicted_delta!))))
const maxTask = computed(() => Math.max(1e-9, ...taskRows.value.map(t => Math.abs(t.predicted_delta))))
function bar(value: number, max: number) { return { width: `${Math.abs(value) / max * 49}%`, left: value >= 0 ? '50%' : `${50 - Math.abs(value) / max * 49}%` } }
watch(() => props.runId, () => { selectedGene.value = ''; selectedTask.value = ''; evidenceFilter.value = 'all' })
watch([() => props.runId, () => entry.value?.record?.status, () => props.focus, projectionOpen], () => {
  if (entry.value?.record?.status !== 'completed') return
  if (props.focus !== 'tasks') runs.ensureTabData(props.runId, 'genes')
  if (props.focus !== 'genes') runs.ensureTabData(props.runId, 'metabolism')
}, { immediate: true })
watch(geneRows, rows => { if (!rows.some(g => g.gene === selectedGene.value)) selectedGene.value = rows[0]?.gene ?? '' }, { immediate: true })
watch(taskRows, rows => { if (!rows.some(t => t.id === selectedTask.value)) selectedTask.value = rows[0]?.id ?? '' }, { immediate: true })
</script>

<template>
  <section class="response-workspace" aria-label="扰动响应概览">
    <div class="response-path"><span><b>01</b> 单细胞状态</span><i>→</i><span><b>02</b> 基因响应</span><i>→</i><span><b>03</b> 代谢功能</span><i>→</i><span><b>04</b> 证据追溯</span></div>
    <details v-if="focus !== 'tasks'" class="projection-preview" :open="projectionOpen" @toggle="projectionOpen=($event.target as HTMLDetailsElement).open"><summary>单细胞 {{ focus === 'all' ? 'UMAP' : 'PCA' }} 科研图：表达分布、基因与功能指标</summary>
    <article v-if="projectionOpen" class="response-panel state-overview" aria-label="单细胞扰动前后状态分布">
      <header><div><span class="micro">STATE / CELL POPULATIONS</span><h2>扰动前后，细胞状态如何分布？</h2></div><span class="panel-index">S</span></header>
      <p class="panel-caption">每个点代表一个细胞的表达状态投影；比较对照群体与扰动后预测群体。</p>
      <CellStateTab :key="runId" :run-id="runId" :embedding="focus === 'all' ? 'umap' : 'pca'" />
    </article>
    </details>
    <p v-if="focus !== 'genes'" class="panel-footnote">模型输入的基因与任务范围已集中展示。<RouterLink :to="{path:'/coverage',query:{run:runId}}">查看基因与任务范围 ↗</RouterLink></p>
    <div class="response-panels" :class="{single: focus !== 'all'}">
      <article v-if="focus !== 'tasks'" class="response-panel">
        <header><div><span class="micro">STATE / EXPRESSION</span><h2>模型预测哪些基因变化最大？</h2></div><span class="panel-index">01</span></header>
        <p class="panel-caption">平均归一化表达差 · 预测 − 对照</p>
        <div v-if="entry?.genes.status === 'error'" class="block-message">基因结果读取失败。<button class="btn btn-sm" @click="runs.retryBlock(runId, 'genes')">重试基因结果</button></div>
        <p v-else-if="entry?.genes.status !== 'ok'" class="block-message">正在读取基因响应…</p>
        <p v-else-if="!geneRows.length" class="block-message">本次运行未提供可比较的基因结果。</p>
        <div v-else class="delta-list" aria-label="基因变化排序">
          <button v-for="row in geneRows" :key="row.gene" type="button" class="delta-row gene-row" :class="{selected: selectedGene === row.gene}" :aria-pressed="selectedGene === row.gene" @click="selectedGene = row.gene"><span class="row-name mono">{{ row.gene }}</span><span class="delta-track" aria-hidden="true"><i :class="{positive: row.predicted_delta! > 0}" :style="bar(row.predicted_delta!, maxGene)"></i></span><strong :class="row.predicted_delta! > 0 ? 'up' : 'down'">{{ fmtDelta(row.predicted_delta, 3) }}</strong></button>
        </div>
        <div class="scale-legend"><span>← 下降</span><span>0</span><span>上升 →</span></div>
        <p class="panel-footnote">显示已加载 {{ genes.length }} 项中变化幅度最大的 {{ geneRows.length }} 项{{ entry?.genes.data?.truncated ? '（接口结果已截断）' : '' }}；排序不代表统计显著性。</p>
        <section v-if="gene" class="gene-detail" aria-label="选中基因详情"><div class="detail-heading"><h3>{{ gene.gene }}</h3><RouterLink :to="{path: '/runs/'+runId, query: {tab:'genes'}}">完整表达结果 ↗</RouterLink></div><dl class="value-triplet"><div><dt>对照表达</dt><dd>{{ fmtNumber(gene.control) }}</dd></div><div><dt>预测表达</dt><dd>{{ fmtNumber(gene.predicted) }}</dd></div><div><dt>变化量</dt><dd>{{ fmtDelta(gene.predicted_delta) }}</dd></div></dl><p v-if="gene.observed_delta !== null" class="panel-footnote">{{ synthetic ? '合成观测差值' : '观测差值' }}：{{ fmtDelta(gene.observed_delta) }}</p></section>
      </article>
      <article v-if="focus !== 'genes'" class="response-panel">
        <header><div><span class="micro">scCellFie / FUNCTION</span><h2>模型预测哪些代谢任务发生变化？</h2></div><span class="panel-index">02</span></header>
        <div class="task-filter"><p class="panel-caption">任务分数差 · 预测 − 对照</p><label v-if="!hasOfficial" class="sr-only" :for="'evidence-filter-'+focus">筛选任务覆盖等级</label><select v-if="!hasOfficial" :id="'evidence-filter-'+focus" v-model="evidenceFilter"><option value="all">全部覆盖等级</option><option value="supported">覆盖支持</option><option value="exploratory">探索性</option><option value="insufficient">证据不足</option></select></div>
        <div v-if="entry?.tasks.status === 'error'" class="block-message">代谢结果读取失败。<button class="btn btn-sm" @click="runs.retryBlock(runId, 'tasks')">重试代谢结果</button></div>
        <p v-else-if="entry?.tasks.status !== 'ok'" class="block-message">正在读取代谢任务…</p>
        <p v-else-if="!taskRows.length" class="block-message">{{ evidenceFilter === 'all' ? '本次运行未提供代谢任务结果。' : '该覆盖等级下没有任务。' }}</p>
        <div v-else class="delta-list" aria-label="代谢任务变化排序"><button v-for="row in taskRows" :key="row.id" type="button" class="delta-row task-row" :class="{selected: selectedTask === row.id}" :aria-pressed="selectedTask === row.id" @click="selectedTask = row.id"><span class="row-name" :title="row.label">{{ row.label }}<small>{{ completenessLabel(row.coverage) }}</small></span><span class="delta-track" aria-hidden="true"><i :class="{positive: row.predicted_delta > 0}" :style="bar(row.predicted_delta, maxTask)"></i></span><strong :class="row.predicted_delta > 0 ? 'up' : 'down'">{{ fmtDelta(row.predicted_delta, 3) }}</strong></button></div>
        <div class="scale-legend"><span>← 下降</span><span>0</span><span>上升 →</span></div>
        <p class="panel-footnote">显示当前筛选 {{ tasks.length }} 项中的前 {{ taskRows.length }} 项{{ entry?.tasks.data?.truncated ? '（接口结果已截断）' : '' }}。{{ entry?.tasks.data?.scope === 'top' ? '当前读取已保存的 Top 摘要。' : '' }}分数不等于通量；两图分别缩放。</p>
        <div v-if="task" class="selected-task"><span class="micro">当前追溯任务</span><strong>{{ task.label }}</strong><span>{{ completenessLabel(task.coverage) }}</span></div>
      </article>
    </div>
    <TaskTrace v-if="task && focus !== 'genes'" :key="runId + ':' + task.id" :run-id="runId" :task-id="task.id" :task-label="task.label" :available="task.trace_available" />
    <p v-for="warning in entry?.summary.data?.warnings ?? []" :key="warning" class="notice notice-warn">{{ warning }}</p>
  </section>
</template>

<style scoped>
.response-workspace{min-width:0}.projection-preview{margin:18px 0}.projection-preview>summary{padding:16px;border:1px solid var(--border);background:var(--card);font-size:12px;color:var(--primary);cursor:pointer}.response-path{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:16px 20px;background:var(--surface-soft);border:1px solid #cedad0;font-size:11px;color:var(--primary-strong)}.response-path b{font:italic 16px Georgia,serif;margin-right:8px}.response-path i{color:#94aaa0;font-style:normal}.coverage-strip{display:flex;gap:22px;flex-wrap:wrap;align-items:center;padding:15px 2px;font-size:11px;color:var(--muted)}.coverage-strip strong{margin-left:8px;color:var(--ink);font:19px Georgia,serif}.coverage-strip small{margin-left:auto;font-size:10px}.response-panels{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}.coverage-strip+.response-panels{margin-top:0}.response-panels.single{grid-template-columns:1fr}.response-panel{background:var(--card);border:1px solid var(--border);padding:22px;min-width:0}.response-panel header{display:flex;justify-content:space-between;align-items:center;gap:12px}.response-panel header .micro{font-size:9px;color:var(--primary);letter-spacing:.12em}.response-panel h2{font-size:18px;font-weight:500;margin:7px 0 0}.panel-index{font:italic 35px Georgia,serif;color:#b1c2b8}.panel-caption{font-size:10px;color:var(--muted);margin:18px 0 12px}.delta-list{border-top:1px solid var(--border)}.delta-row{width:100%;display:grid;grid-template-columns:minmax(65px,1fr) minmax(50px,1fr) 70px;align-items:center;gap:10px;min-height:45px;text-align:left;border:0;border-bottom:1px solid #e6e8e1;padding:8px;background:transparent;color:var(--ink);font:inherit;cursor:pointer}.delta-row:hover{background:var(--surface-soft)}.delta-row.selected{background:var(--primary-weak);box-shadow:inset 2px 0 var(--primary)}.delta-row strong{font:12px Consolas,monospace;text-align:right}.row-name{font-size:12px;overflow-wrap:anywhere}.row-name small{display:block;font-size:9px;color:var(--muted);margin-top:3px}.task-row{grid-template-columns:minmax(100px,1.6fr) minmax(38px,1fr) 64px;min-height:54px}.task-row .row-name{font-size:11px}.delta-track{height:24px;position:relative;background:linear-gradient(to right,transparent 49.5%,#c7cfca 49.5%,#c7cfca 50.5%,transparent 50.5%)}.delta-track i{position:absolute;top:7px;height:10px;background:var(--delta-down)}.delta-track i.positive{background:var(--delta-up)}.up{color:#aa5130}.down{color:#357f78}.scale-legend{display:flex;justify-content:space-between;color:var(--muted);font-size:9px;padding:8px}.panel-footnote{font-size:10px;color:var(--muted);line-height:1.8;margin:12px 0}.block-message{min-height:190px;display:flex;align-items:center;justify-content:center;gap:10px;font-size:12px;color:var(--muted)}.task-filter{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}.task-filter select{max-width:100%;font:10px var(--font);color:var(--muted);border:1px solid var(--border);background:var(--card);padding:4px}.detail-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.detail-heading h3{font-size:14px;font-weight:500}.detail-heading a{font-size:10px}.gene-detail{border-top:1px solid var(--border);padding-top:18px;margin-top:18px}.value-triplet{display:grid;grid-template-columns:repeat(3,1fr);margin:15px 0 0;gap:8px}.value-triplet dt{font-size:9px;color:var(--muted)}.value-triplet dd{font:18px Georgia,serif;margin:5px 0 0;overflow-wrap:anywhere}.selected-task{display:flex;flex-direction:column;gap:8px;border-top:1px solid var(--border);padding-top:15px;margin-top:15px}.selected-task strong{font-size:12px;font-weight:500}.selected-task>span{font-size:10px;color:var(--muted)}@media(max-width:1150px){.response-panels{grid-template-columns:1fr}.coverage-strip{gap:12px}.coverage-strip small{margin-left:0}}@media(max-width:600px){.response-panel{padding:16px}.response-path{padding:12px 10px;gap:4px;font-size:9px}.response-path b{display:block;margin:0}.response-panel h2{font-size:16px}.coverage-strip strong{font-size:16px}}
</style>
