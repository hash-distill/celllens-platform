<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '../api/http'
import { useRunStore } from '../stores/run'
import { accessSession } from '../stores/access'
import { openAssistant } from '../stores/assistantSource'
import type { MeasuredComparison } from '../types/comparison'
import type { CoverageCatalogue } from '../types/coverage'
import type { ResearchSelection, ResearchResult } from '../types/research'
import type { StructureTask } from '../utils/researchCanvas'
import type { OverviewRow } from '../utils/resultOverview'
import { finiteValue } from '../utils/resultOverview'
import { metabolicGroupName, taskName } from '../utils/biologyLocale'
import { isSyntheticResult } from '../utils/source'
import ResultOverview from './ResultOverview.vue'
import CellStateTab from './tabs/CellStateTab.vue'
import ResearchCanvas from './ResearchCanvas.vue'

const props = defineProps<{ runId: string; originalResult?: ResearchResult | null }>()
const emit = defineEmits<{ 'comparison-mode': [matched: boolean]; 'focus-task': [id: string]; selection: [value: ResearchSelection] }>()
const runs = useRunStore(), route = useRoute(), router = useRouter()
const readOnly = computed(() => Boolean(accessSession.value?.read_only))
const entry = computed(() => runs.entry(props.runId))
const record = computed(() => entry.value?.record)
const comparison = ref<MeasuredComparison | null>(null)
const coverage = ref<CoverageCatalogue | null>(null)
const loading = ref(false), comparisonError = ref(''), coverageError = ref('')
const projectionOpen = ref(false)
const synthetic = computed(() => isSyntheticResult(record.value?.request.mode, props.runId, record.value?.result_kind))
let controller: AbortController | undefined
let retryTimer: ReturnType<typeof setTimeout> | undefined
const matched = computed(() => comparison.value?.status === 'available' ? comparison.value : null)
watch(() => matched.value !== null, available => emit('comparison-mode', available), { immediate: true, flush: 'sync' })
const originalGenes = computed(() => entry.value?.genes.data?.items ?? [])
const samePanel = computed(() => {
  if (!matched.value || entry.value?.genes.status !== 'ok' || entry.value.genes.data?.truncated) return false
  const matchedIds = new Set((matched.value.genes ?? []).map(row => row.id))
  return matchedIds.size === originalGenes.value.length && originalGenes.value.every(row => matchedIds.has(row.gene))
})
const targetInPanel = computed(() => {
  if (entry.value?.genes.status !== 'ok' || !record.value) return null
  const target = record.value.request.perturbation.toUpperCase()
  if (originalGenes.value.some(row => row.gene.toUpperCase() === target)) return true
  return entry.value.genes.data?.truncated ? null : false
})
const genes = computed<OverviewRow[]>(() => matched.value
  ? (matched.value.genes ?? []).map(row => ({ id: row.id, control: finiteValue(row.control), predicted: finiteValue(row.predicted), observed: finiteValue(row.observed), delta: finiteValue(row.predicted_delta) }))
  : originalGenes.value.map(row => ({ id: row.gene, control: row.control, predicted: row.predicted, observed: null, delta: row.predicted_delta })))
const tasks = computed<StructureTask[]>(() => {
  const original = new Map((entry.value?.tasks.data?.items ?? []).map(row => [row.id, row]))
  const paired = new Map((matched.value?.tasks ?? []).map(row => [row.id, row]))
  const metadata = new Map((coverage.value?.tasks ?? []).map(row => [row.id, row]))
  const ids = new Set([...metadata.keys(), ...(matched.value ? paired.keys() : original.keys())])
  return [...ids].map(id => {
    const detail = metadata.get(id), saved = original.get(id)
    const value = matched.value ? paired.get(id) : saved
    const control = finiteValue(value?.control), predicted = finiteValue(value?.predicted)
    return {
      id, label: taskName(id, detail?.label ?? saved?.label),
      category: metabolicGroupName(detail?.category ?? saved?.category),
      rawCategory: detail?.category ?? saved?.category,
      control, predicted,
      observed: matched.value ? finiteValue(paired.get(id)?.observed) : null,
      delta: control !== null && predicted !== null ? finiteValue(predicted - control) : null,
      coverage: !matched.value || samePanel.value ? finiteValue(detail?.fraction_present_all) ?? (readOnly.value && entry.value?.tasks.data?.scope === 'all' && !entry.value.tasks.data.truncated ? finiteValue(saved?.coverage) : null) : null,
    }
  })
})
const originalGroups = computed(() => props.originalResult?.record_id === props.runId ? props.originalResult.populations?.original.groups ?? props.originalResult.groups : [])
const populationCounts = computed(() => matched.value?.parameters?.population_counts ?? matched.value?.population_matching?.selected_cells ?? Object.fromEntries(originalGroups.value.map(group => [group.id, group.count])))
const baselineSensitive = computed(() => matched.value?.batch_sensitivity?.status === 'available' && typeof matched.value.batch_sensitivity.baseline_conclusion_consistent === 'boolean' ? !matched.value.batch_sensitivity.baseline_conclusion_consistent : null)
const geneCount = computed(() => matched.value ? matched.value.genes?.length ?? null : entry.value?.genes.data?.truncated ? null : originalGenes.value.length || null)
const baselineRatio = computed(() => finiteValue(matched.value?.expression?.mse_relative_to_no_change))

async function loadContext() {
  clearTimeout(retryTimer)
  controller?.abort()
  const current = controller = new AbortController(), runId = props.runId
  comparison.value = null; coverage.value = null; comparisonError.value = ''; coverageError.value = ''; loading.value = true
  if (synthetic.value || readOnly.value) { loading.value = false; return }
  const results = await Promise.allSettled([
    apiFetch<MeasuredComparison>(`/runs/${encodeURIComponent(runId)}/comparison`, { signal: current.signal, timeoutMs: 120000 }),
    apiFetch<CoverageCatalogue>('/coverage', { query: { run_id: runId }, signal: current.signal }),
  ])
  if (current.signal.aborted || runId !== props.runId) return
  const comparisonResult = results[0], coverageResult = results[1]
  if (comparisonResult.status === 'fulfilled') {
    const data = comparisonResult.value
    if (data.run_id !== runId || data.cell_line !== record.value?.request.cell_line || data.perturbation !== record.value?.request.perturbation) comparisonError.value = '实测比较的研究条件不匹配，已停止展示。'
    else {
      comparison.value = data
      if (data.status === 'preparing') retryTimer = setTimeout(() => void loadContext(), 5000)
    }
  } else comparisonError.value = comparisonResult.reason instanceof Error ? comparisonResult.reason.message : '实测比较读取失败'
  if (coverageResult.status === 'fulfilled') coverage.value = coverageResult.value
  else coverageError.value = '任务关联基因覆盖暂不可用，覆盖将标记为未知。'
  loading.value = false
}
watch([() => props.runId, readOnly], () => {
  projectionOpen.value = false
  const current = entry.value
  if (current?.genes.status === 'idle') void runs.loadGenes(props.runId)
  if (current?.tasks.status === 'idle') void runs.loadTasks(props.runId)
  void loadContext()
}, { immediate: true })
onBeforeUnmount(() => { controller?.abort(); clearTimeout(retryTimer) })
function openDetail(kind: 'gene' | 'task', id: string) {
  if (readOnly.value) return
  if (kind === 'task' && !entry.value?.tasks.data?.items.some(task => task.id === id)) {
    void router.replace({ path: '/methods/coverage', query: { run: props.runId, task: id } })
    return
  }
  void router.replace({ path: route.path, query: {
    ...route.query, tab: kind === 'gene' ? 'genes' : 'metabolism',
    gene: kind === 'gene' ? id : undefined, task: kind === 'task' ? id : undefined,
    view: kind === 'task' ? 'function' : undefined,
  } })
}
</script>

<template>
  <section class="run-result-overview" aria-label="预测结果概览">
    <p v-if="synthetic" class="notice notice-warn">当前为合成示例，仅用于展示软件交互。</p>
    <div v-else class="comparison-context" role="status">
      <p v-if="readOnly">公开展览使用原冻结群体；私有比较不公开。完整分析在私人工作区中进行。</p>
      <p v-else-if="loading">正在核对可用实测与任务覆盖；当前展示原运行结果。</p>
      <p v-else-if="comparisonError" class="context-error">实测比较读取失败：{{ comparisonError }} <button type="button" @click="loadContext">重试</button></p>
      <p v-else-if="matched">当前概览使用匹配比较的同一基因面板与选定群体：对照、模型预测、扰动实测。表达为 mean(log1p(CP10K))；任务为表达派生分数。</p>
      <p v-else>{{ comparison?.reason || '暂无匹配实测比较，当前展示原运行的对照与模型预测。' }}</p>
      <p v-if="matched">这是匹配观测诊断，不代表独立留出验证。<button type="button" @click="router.replace({path:route.path,query:{...route.query,tab:'comparison'}})">查看完整核对 →</button></p>
      <p v-if="matched && !samePanel">尚未确认与原运行面板完全一致，任务关联基因覆盖暂记为未知。</p>
      <p v-if="coverageError" class="context-error">{{ coverageError }} <button type="button" @click="loadContext">重试</button></p>
    </div>
    <div v-if="!matched" class="load-notices">
      <p v-if="entry?.genes.status === 'loading' || entry?.tasks.status === 'loading'" role="status">正在读取表达与代谢任务结果…</p>
      <p v-if="entry?.genes.status === 'error'" role="alert">表达结果读取失败。<button type="button" @click="runs.retryBlock(runId, 'genes')">重试表达结果</button></p>
      <p v-if="entry?.tasks.status === 'error'" role="alert">代谢结果读取失败。<button type="button" @click="runs.retryBlock(runId, 'tasks')">重试代谢结果</button></p>
      <p v-if="entry?.genes.data?.truncated || entry?.tasks.data?.truncated">当前已加载的原运行结果不完整；可进入详细表格或导出完整记录。</p>
    </div>
    <ResultOverview :read-only="readOnly" source-kind="run" :cell-line="record?.request.cell_line ?? ''" :perturbation="record?.request.perturbation ?? ''" :genes="genes" :tasks="tasks" :counts="populationCounts" :baseline-ratio="baselineRatio" :baseline-sensitive="baselineSensitive" :gene-count="geneCount" :source-label="matched ? '匹配群体：模型预测与实测诊断' : '原运行群体：对照与模型预测'" :expression-units="matched ? 'mean(log1p(CP10K))' : originalResult?.units.expression || undefined" :target-in-panel="targetInPanel" @select-gene="openDetail('gene', $event)" @select-task="openDetail('task', $event)" @interpret="openAssistant(false)" @focus-task="emit('focus-task', $event)"><template #landscape><ResearchCanvas v-if="!synthetic" kind="prediction" :record-id="runId" :tasks="tasks" :read-only="readOnly" :knowledge-version="coverage?.database_version" @selection="emit('selection',$event)" @select-task="openDetail('task',$event)" /></template></ResultOverview>
    <details v-if="!readOnly" class="projection-inspection" :open="projectionOpen" @toggle="projectionOpen = ($event.target as HTMLDetailsElement).open">
      <summary>进一步检查：表达状态分布 <span>共同坐标中的群体差异</span></summary>
      <div v-if="projectionOpen" class="projection-content"><p>点表示各组表达记录，不表示细胞形态或运动轨迹。分布图有独立的群体选择与尺度，请按图内说明核对。</p><CellStateTab :key="runId" :run-id="runId" embedding="umap" /></div>
    </details>
  </section>
</template>

<style scoped>
.comparison-context{font-size:11px;line-height:1.9;color:var(--muted);margin:0 0 16px;padding:12px 16px;border-left:2px solid var(--border-strong);background:var(--surface-soft)}.comparison-context p{margin:3px 0}.comparison-context button,.load-notices button{border:0;background:transparent;color:var(--primary-strong);font:inherit;cursor:pointer;padding:0 5px;text-decoration:underline;text-underline-offset:3px}.context-error{color:#a36432}.load-notices{font-size:12px;color:var(--muted);line-height:1.8}.projection-inspection{border:1px solid var(--border);background:var(--card);margin:20px 0}.projection-inspection>summary{padding:17px 22px;color:var(--primary-strong);font-size:12px;cursor:pointer}.projection-inspection>summary span{margin-left:16px;font-size:10px;color:var(--muted)}.projection-content{padding:20px;border-top:1px solid var(--border)}.projection-content>p{margin:0 0 18px;font-size:11px;line-height:1.8;color:var(--muted)}button:focus-visible{outline:2px solid var(--primary);outline-offset:3px}
</style>
