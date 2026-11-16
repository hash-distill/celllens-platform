<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { measuredApi } from '../api/measured'
import { apiFetch, ApiError } from '../api/http'
import UiIcon from '../components/UiIcon.vue'
import type { ResearchSelection } from '../types/research'
import MeasuredProjection from '../components/MeasuredProjection.vue'
import ResultOverview from '../components/ResultOverview.vue'
import ResearchCanvas from '../components/ResearchCanvas.vue'
import ResearchEvidence from '../components/ResearchEvidence.vue'
import MeasuredTaskEvidence from '../components/MeasuredTaskEvidence.vue'
import { useAssistantSource, openAssistant } from '../stores/assistantSource'
import { accessSession } from '../stores/access'
import { metabolicGroupName, taskName } from '../utils/biologyLocale'
import type { AssistantSelection } from '../api/assistant'
import { downloadBlob } from '../utils/csv'
import { fmtServerTime } from '../utils/format'
import type { MeasuredAnalysis, MeasuredCellLine, MeasuredDownloadKind, MeasuredProjection as Projection, MeasuredRequest, MeasuredRow, MeasuredStatus, MeasuredTable, MeasuredTableKind } from '../types/measured'

const route = useRoute(), router = useRouter()
const readOnly = computed(() => Boolean(accessSession.value?.read_only))
const labels: Record<MeasuredStatus, string> = { queued: '等待分析', preparing: '准备实测数据', analysing: '分析中', completed: '已完成', failed: '分析失败', cancelled: '已取消', interrupted: '分析中断' }
const selected = ref<MeasuredAnalysis | null>(null), recordLoading = ref(false), recordError = ref('')
const submitting = ref(false), cancelling = ref(false), actionError = ref(''), uncertain = ref(false)
const projectionOpen = ref(false), tableOpen = ref(false)
const tableSection = ref<HTMLElement | null>(null)
const overviewTasks = ref<MeasuredRow[]>([]), overviewError = ref(''), overviewLoading = ref(false), overviewRefresh = ref(0)
const selectedFeature = ref<AssistantSelection>({view:'overview'})
const focusedTask=ref('')
const canvasSelection = ref<ResearchSelection>({layer:'expression'})
const expressionSelection = ref<ResearchSelection>({layer:'expression',projection_id:'pca'})
const taskEvidenceSection = ref<HTMLElement | null>(null)
const activeEvidenceTask = computed(() => selectedFeature.value.feature_kind === 'task' ? selectedFeature.value.feature_id || '' : focusedTask.value)
const tabs = [{ key: 'overview', label: '研究总览' }, { key: 'genes', label: '表达响应' }, { key: 'metabolism', label: '功能证据' }, { key: 'comparison', label: '实验对照' }] as const
type ResultTab = typeof tabs[number]['key']
const activeTab = computed<ResultTab>(() => route.query.tab === 'function' ? 'metabolism' : tabs.some(tab => tab.key === route.query.tab) ? route.query.tab as ResultTab : 'overview')
const selectionLayers: Record<ResultTab, ResearchSelection['layer']> = { overview: 'structure', genes: 'expression', metabolism: 'function', comparison: 'expression' }
const researchSelection=computed<ResearchSelection>(()=>({gene_id:selectedFeature.value.feature_kind==='gene'?selectedFeature.value.feature_id:undefined,task_id:selectedFeature.value.feature_kind==='task'?selectedFeature.value.feature_id:focusedTask.value||undefined,layer:selectionLayers[activeTab.value],...(activeTab.value==='overview'?canvasSelection.value:activeTab.value==='genes'?expressionSelection.value:{})}))
const tableKind = ref<MeasuredTableKind>('genes'), tableSearch = ref(''), appliedSearch = ref(''), tablePage = ref(1), table = ref<MeasuredTable | null>(null), tableLoading = ref(false), tableError = ref('')
const embedding = ref<'pca' | 'umap'>('pca'), projection = ref<Projection | null>(null), projectionLoading = ref(false), projectionError = ref('')
watch(embedding, value => { expressionSelection.value = {layer:'expression',projection_id:value} })
const downloading = ref<MeasuredDownloadKind | null>(null)
const tableRefresh = ref(0), projectionRefresh = ref(0)
const lifetime = new AbortController()
let pollTimer: number | undefined, recordController: AbortController | undefined
const analysisId = computed(() => typeof route.params.analysisId === 'string' ? route.params.analysisId : '')
const active = computed(() => selected.value ? isActive(selected.value.status) : false)
const summary = computed(() => selected.value?.status === 'completed' ? selected.value.summary : null)
const progress = computed(() => Math.min(100, Math.max(0, selected.value?.progress ?? 0)))
const projectionAvailable = computed(() => summary.value?.projections?.[embedding.value]?.available ?? false)
const metabolismAvailable = computed(() => summary.value?.metabolism.available ?? false)
const tablePages = computed(() => Math.max(1, Math.ceil((table.value?.total ?? 0) / 20)))
const units = computed(() => typeof table.value?.units === 'string' ? table.value.units : tableKind.value === 'genes' ? summary.value?.expression_units : '表达推断的代谢评分')
const batchDetails = computed(() => Object.entries(summary.value?.batch_matching ?? {}))
const provenanceDetails = computed(() => Object.entries(summary.value?.provenance ?? {}))
function sourceObject(value: unknown): Record<string, unknown> { return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {} }
const sourceIdentity = computed(() => ({ ...sourceObject(summary.value?.provenance.source), ...selected.value?.source }))
const importId = computed(() => {
  const value = selected.value?.import_id ?? sourceIdentity.value.import_id
  return typeof value === 'string' && value.trim() ? value : null
})
function publicCellLine(value: string): value is MeasuredCellLine { return ['K562', 'RPE1', 'Jurkat', 'HepG2'].includes(value) }
const imported = computed(() => Boolean(importId.value) || (sourceIdentity.value.kind === 'controlled_private_h5ad' || sourceIdentity.value.type === 'controlled_private_h5ad') || Boolean(selected.value && !publicCellLine(selected.value.cell_line)))
const sourceLabel = computed(() => imported.value ? '自有 H5AD · 实测数据' : '公开 Perturb-seq · 实测数据')
const reuseTarget = computed(() => imported.value ? { path: '/research', query: { type: 'import' } } : { path: '/research', query: { type: 'measured', cell_line: selected.value?.cell_line, perturbation: selected.value?.perturbation, max_cells: String(selected.value?.max_cells ?? ''), seed: String(selected.value?.seed ?? '') } })
const missingImport = ref(false)
function selectTab(tab: ResultTab) { return router.replace({ path: route.path, query: { ...route.query, tab: tab === 'overview' ? undefined : tab } }) }
async function navigateTab(event: KeyboardEvent) {
  const index = tabs.findIndex(tab => tab.key === activeTab.value)
  const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : -1
  if (next < 0) return
  event.preventDefault()
  await selectTab(tabs[next].key)
  await nextTick()
  document.getElementById(`measured-tab-${tabs[next].key}`)?.focus()
}
useAssistantSource(() => !readOnly.value && selected.value ? {
  kind:'measured', id:selected.value.id, title:`${selected.value.cell_line} · ${selected.value.perturbation}`,
  completed:selected.value.status === 'completed', view:selectedFeature.value.view, selection:selectedFeature.value,
} : null)
const overviewGenes = computed(() => (summary.value?.top_genes ?? []).map(row => ({id:row.gene ?? '', control:row.control, observed:row.observed, delta:row.observed_delta})))
const overviewTaskRows = computed(() => overviewTasks.value.map(row => ({id:row.task ?? '', label:taskName(row.task ?? '', row.label), category:metabolicGroupName(row.category ?? undefined), rawCategory:row.category, control:row.control, observed:row.observed, delta:row.observed_delta, coverage:row.gene_fraction})))
async function selectFeature(kind:'gene'|'task', id:string) {
  await selectTab(kind === 'gene' ? 'genes' : 'metabolism')
  selectedFeature.value = {view:kind === 'gene' ? 'genes' : 'metabolism', feature_kind:kind, feature_id:id}
  if (kind === 'task') focusedTask.value = id
  tableKind.value = kind === 'gene' ? 'genes' : 'tasks'; tableSearch.value = id; appliedSearch.value = id; tablePage.value = 1; tableOpen.value = true
  await nextTick()
  ;(kind === 'task' ? taskEvidenceSection.value : tableSection.value)?.scrollIntoView({block:'start', behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'})
}
function isActive(status: MeasuredStatus) { return ['queued', 'preparing', 'analysing'].includes(status) }
function errorText(error: unknown) { return error instanceof Error ? error.message : '读取失败，请重试' }
function numeric(value: number | null | undefined) { return value == null || !Number.isFinite(value) ? '—' : value.toLocaleString('zh-CN', { maximumFractionDigits: 5 }) }
function rowLabel(row: MeasuredRow) { return row.task ? taskName(row.task, row.label) : row.gene ?? row.reaction ?? '' }
function selectedFeatureLabel() { const feature = selectedFeature.value; return feature.feature_kind === 'task' ? taskName(feature.feature_id ?? '') : feature.feature_id }
function rowId(row: MeasuredRow) { return row.gene ?? row.task ?? row.reaction ?? '' }
function detailValue(value: unknown): string { return typeof value === 'string' ? value : JSON.stringify(value, null, 2) ?? '—' }
function clearPolling() { if (pollTimer !== undefined) window.clearTimeout(pollTimer); pollTimer = undefined; recordController?.abort() }

async function loadRecord(id = analysisId.value) {
  if (!id) return
  clearPolling(); const controller = new AbortController(); recordController = controller
  recordLoading.value = true; recordError.value = ''
  try {
    const record = await measuredApi.get(id, controller.signal)
    if (controller.signal.aborted) return
    selected.value = record
    if (isActive(record.status)) pollTimer = window.setTimeout(() => { void loadRecord(id) }, 2000)
  } catch (error) { if (!controller.signal.aborted) recordError.value = errorText(error) }
  finally { if (!controller.signal.aborted) recordLoading.value = false }
}
watch(analysisId, (id) => {
  clearPolling(); missingImport.value=false;focusedTask.value='';selected.value = null; recordError.value = ''; recordLoading.value = false
  canvasSelection.value={layer:'expression'}; expressionSelection.value={layer:'expression',projection_id:'pca'}
  selectedFeature.value = {view:'overview'}; projectionOpen.value = false; tableOpen.value = false
  tableKind.value = 'genes'; tablePage.value = 1; tableSearch.value = ''; appliedSearch.value = ''; embedding.value = 'pca'
  if (id) void loadRecord(id)
}, { immediate: true })
watch([activeTab, () => summary.value?.analysis_id], ([tab]) => {
  selectedFeature.value = { ...selectedFeature.value, view: tab }
  projectionOpen.value = tab === 'genes'
  tableOpen.value = tab === 'genes' || tab === 'metabolism'
  const kind = tab === 'genes' ? 'genes' : tab === 'metabolism' && tableKind.value === 'genes' ? 'tasks' : tableKind.value
  if (kind !== tableKind.value) { tableKind.value = kind; tablePage.value = 1; tableSearch.value = ''; appliedSearch.value = '' }
}, { immediate: true })

async function start(payload: MeasuredRequest) {
  if (submitting.value || uncertain.value || active.value) return
  submitting.value = true; actionError.value = ''
  let postStarted = false
  try {
    // Revalidate source on explicit submission, including a retry of a historical analysis.
    const source = await measuredApi.coverage(payload.cell_line, payload.perturbation, lifetime.signal)
    if (source.source_status !== 'measured') throw new Error('当前固定源未确认该组合的实测数据，请先查看数据目录')
    postStarted = true
    const record = await measuredApi.create(payload, lifetime.signal)
    if (lifetime.signal.aborted) return
    await router.push(`/measured/${encodeURIComponent(record.id)}`)
  } catch (error) {
    if (lifetime.signal.aborted) return
    actionError.value = errorText(error)
    if (postStarted && error instanceof ApiError && ['network', 'timeout'].includes(error.kind)) { uncertain.value = true }
  } finally { if (!lifetime.signal.aborted) submitting.value = false }
}
async function cancel() {
  if (!selected.value || !active.value || cancelling.value) return
  const id = selected.value.id; cancelling.value = true; actionError.value = ''
  try { const record = await measuredApi.cancel(id, lifetime.signal); if (!lifetime.signal.aborted && analysisId.value === id) { selected.value = record; clearPolling(); if (isActive(record.status)) void loadRecord(id) } }
  catch (error) { if (!lifetime.signal.aborted) actionError.value = errorText(error) }
  finally { if (!lifetime.signal.aborted) cancelling.value = false }
}
async function retry() {
  if (readOnly.value || !selected.value || submitting.value || uncertain.value || active.value) return
  if (!imported.value && publicCellLine(selected.value.cell_line)) {
    await start({ cell_line: selected.value.cell_line, perturbation: selected.value.perturbation, max_cells: selected.value.max_cells, seed: selected.value.seed })
    return
  }
  if (!importId.value) {
    missingImport.value = true
    actionError.value = '此记录缺少可核验的自有数据版本，无法复用。请回到自有数据入口重新选择并核验文件。'
    return
  }
  submitting.value = true; actionError.value = ''
  try {
    const record = await apiFetch<MeasuredAnalysis>(`/research/imports/${encodeURIComponent(importId.value)}/analyses`, { method: 'POST', signal: lifetime.signal })
    if (!lifetime.signal.aborted) await router.push(`/measured/${encodeURIComponent(record.id)}`)
  } catch (error) {
    if (!lifetime.signal.aborted) {
      actionError.value = errorText(error)
      if (error instanceof ApiError && ['network', 'timeout'].includes(error.kind)) uncertain.value = true
    }
  } finally { if (!lifetime.signal.aborted) submitting.value = false }
}

watch([() => summary.value?.analysis_id, tableKind, appliedSearch, tablePage, tableRefresh, tableOpen], async (_value, _old, cleanup) => {
  const controller = new AbortController(); cleanup(() => controller.abort()); table.value = null; tableError.value = ''; tableLoading.value = false
  if (!tableOpen.value || !summary.value || (tableKind.value !== 'genes' && !metabolismAvailable.value)) return
  tableLoading.value = true
  try { const result = await measuredApi.table(analysisId.value, tableKind.value, appliedSearch.value, 20, (tablePage.value - 1) * 20, controller.signal); if (!controller.signal.aborted) table.value = result }
  catch (error) { if (!controller.signal.aborted) tableError.value = errorText(error) }
  finally { if (!controller.signal.aborted) tableLoading.value = false }
})
watch([() => summary.value?.analysis_id, overviewRefresh], async (_value, _old, cleanup) => {
  const controller = new AbortController(); cleanup(() => controller.abort())
  overviewTasks.value = []; overviewError.value = ''; overviewLoading.value = false
  if (!summary.value?.metabolism.available) return
  overviewLoading.value = true
  try {
    const rows: MeasuredRow[] = []
    let total = 1
    while (rows.length < total) {
      const result = await measuredApi.table(analysisId.value, 'tasks', '', 200, rows.length, controller.signal)
      if (controller.signal.aborted) return
      total = result.total
      if (!result.items.length && rows.length < total) throw new Error('任务分页不完整，请重试')
      rows.push(...result.items)
    }
    overviewTasks.value = rows
  } catch (error) { if (!controller.signal.aborted) overviewError.value = errorText(error) }
  finally { if (!controller.signal.aborted) overviewLoading.value = false }
})
watch([() => summary.value?.analysis_id, embedding, projectionRefresh, projectionOpen], async (_value, _old, cleanup) => {
  const controller = new AbortController(); cleanup(() => controller.abort()); projection.value = null; projectionError.value = ''; projectionLoading.value = false
  if (!summary.value || !projectionAvailable.value || !projectionOpen.value) return
  projectionLoading.value = true
  try { const result = await measuredApi.projection(analysisId.value, embedding.value, controller.signal); if (!controller.signal.aborted) projection.value = result }
  catch (error) { if (!controller.signal.aborted) projectionError.value = errorText(error) }
  finally { if (!controller.signal.aborted) projectionLoading.value = false }
})
function clearFeature() { focusedTask.value = ''; selectedFeature.value = { view: activeTab.value }; tableSearch.value = ''; appliedSearch.value = ''; tablePage.value = 1 }
function focusRow(row: MeasuredRow) {
  if (tableKind.value === 'reactions') return
  const kind = tableKind.value === 'genes' ? 'gene' : 'task'
  selectedFeature.value = { view: activeTab.value, feature_kind: kind, feature_id: rowId(row) }
  if (kind === 'task') focusedTask.value = rowId(row)
}
function searchTable() { appliedSearch.value = tableSearch.value.trim(); tablePage.value = 1 }
function changeKind(kind: MeasuredTableKind) { selectedFeature.value = {view:kind==='genes'?'genes':'metabolism'}; tableKind.value = kind; tablePage.value = 1; tableSearch.value = ''; appliedSearch.value = '' }
async function download(kind: MeasuredDownloadKind) {
  if (readOnly.value || !selected.value || downloading.value) return
  downloading.value = kind; actionError.value = ''
  try { const file = await measuredApi.download(selected.value.id, kind, lifetime.signal); if (!lifetime.signal.aborted) downloadBlob(file.blob, file.filename) }
  catch (error) { if (!lifetime.signal.aborted) actionError.value = errorText(error) }
  finally { if (!lifetime.signal.aborted) downloading.value = null }
}
onBeforeUnmount(() => { lifetime.abort(); clearPolling() })
</script>

<template>
  <div class="page measured-page national-page">
    <header v-if="!selected" class="page-heading"><div><span class="eyebrow">MEASURED PERTURBATION ANALYSIS</span><h1>实测研究工作台</h1><p>比较实测对照与扰动，查看表达变化、功能线索与可追溯证据。</p></div><RouterLink :to="readOnly?'/records?category=measured':'/research?type=measured'" class="btn">{{readOnly?'浏览实测案例':'新建实测分析'}}</RouterLink></header>
    <nav v-if="selected" class="result-breadcrumb" aria-label="研究路径"><RouterLink to="/">研究概览</RouterLink><span>/</span><RouterLink to="/records?category=measured">实测研究记录</RouterLink><span>/</span><strong>研究工作台</strong></nav>
    <div class="analysis-layout result-layout">
      <div class="analysis-content">
        <div v-if="actionError" class="notice notice-danger" role="alert">{{ actionError }} <RouterLink v-if="missingImport" to="/research?type=import" class="btn btn-sm">返回自有数据入口</RouterLink></div>
        <div v-if="uncertain" class="notice" role="alert"><p>提交结果待确认，请先核对实验记录，避免重复创建。页面不会自动重发请求。</p><div class="btn-row"><RouterLink to="/records?category=measured" class="btn btn-sm">核对实测记录</RouterLink><button class="btn btn-sm" @click="uncertain = false">已核对记录，允许再次提交</button></div></div>
        <section v-if="recordError" class="card empty-state" role="alert"><h2>分析记录读取失败</h2><p>{{ recordError }}</p><button class="btn" @click="loadRecord()">重新读取</button></section>
        <section v-else-if="recordLoading && !selected" class="card empty-state" role="status">正在读取分析记录…</section>
        <section v-else-if="!selected" class="card empty-state"><span class="eyebrow">OBSERVED EXPRESSION</span><h2>从真实扰动数据开始</h2><p>选择细胞背景和扰动基因，明确启动分析后生成结果。完整共同基因面板用于表达比较，不限定为模型的 2,000 个高变基因。</p><p>结果包含实测组均值、扰动减对照的差值，以及可用的投影与表达推断代谢评分。</p></section>
        <template v-if="selected">
          <section class="card status-card" aria-live="polite">
            <div class="section-heading result-identity-heading"><div><span class="eyebrow">PERTURBATION EXPLORER · {{ sourceLabel }}</span><h1>{{ selected.cell_line }} <span class="identity-divider">/</span> {{ selected.perturbation }} <span class="status-tag" :class="selected.status">{{ labels[selected.status] }}</span></h1><small>{{ fmtServerTime(selected.created_at) }} · 目标实测上限 {{ selected.max_cells }} · 种子 {{ selected.seed }}</small><p class="result-identity mono">{{ selected.id }}</p></div><div v-if="!readOnly" class="result-primary-actions btn-row"><RouterLink to="/research" class="btn btn-sm">＋ 新建分析</RouterLink><details class="result-action-menu" @keydown.esc="($event.currentTarget as HTMLDetailsElement).open=false"><summary class="btn btn-sm"><UiIcon name="export" :size="14"/> 导出与更多 <span aria-hidden="true">⌄</span></summary><div class="result-action-popover"><span class="action-menu-label">研究操作</span><button class="result-menu-item" :disabled="recordLoading" @click="loadRecord()"><UiIcon name="reset" :size="15"/>刷新运行状态</button><RouterLink :to="reuseTarget" class="result-menu-item"><UiIcon name="layers" :size="15"/>{{ imported ? '进入自有数据分析' : '复用本次参数' }}</RouterLink><RouterLink to="/records?category=measured" class="result-menu-item"><UiIcon name="file" :size="15"/>查看实测记录</RouterLink><template v-if="summary"><div class="action-menu-divider"/><span class="action-menu-label">结果与来源</span><button class="result-menu-item" :disabled="!!downloading" @click="download('bundle')"><UiIcon name="export" :size="15"/>{{ downloading === 'bundle' ? '完整结果下载中…' : '完整结果与来源 · ZIP' }}</button><button class="result-menu-item" :disabled="!!downloading" @click="download('report')"><UiIcon name="file" :size="15"/>{{ downloading === 'report' ? '报告下载中…' : '阅读报告 · HTML' }}</button><button class="result-menu-item" :disabled="!!downloading" @click="download('genes')">完整表达表 · CSV</button><button class="result-menu-item" :disabled="!!downloading || !metabolismAvailable" @click="download('tasks')">完整任务表 · CSV</button><button class="result-menu-item" :disabled="!!downloading || !metabolismAvailable" @click="download('reactions')">完整反应表 · CSV</button></template></div></details></div></div>
            <template v-if="active"><progress :value="progress" max="100" :aria-label="`分析进度 ${progress}%`"/><p>{{ selected.message || '分析任务已接收' }} · {{ numeric(progress) }}%</p><div class="btn-row"><button class="btn" :disabled="cancelling" @click="cancel">{{ cancelling ? '正在取消…' : '取消分析' }}</button><small>离开本页后，后台分析仍会继续。</small></div></template>
            <template v-else-if="selected.status !== 'completed'"><p role="status">{{ selected.error_message || selected.message || '本次分析没有可用结果。可以重新创建一次分析。' }}</p><button class="btn" :disabled="submitting || uncertain" @click="retry">重新分析</button></template>
            <p v-else-if="!summary" class="notice">记录已完成，但没有可读取的结果摘要。<button class="btn btn-sm" @click="loadRecord()">重新读取</button></p>
          </section>
          <template v-if="summary">
            <ResearchEvidence kind="measured" :record-id="selected.id" :selection="researchSelection" completed />
            <div class="tabs result-tabs" role="tablist" aria-label="实测研究结果" @keydown="navigateTab"><button v-for="tab in tabs" :id="`measured-tab-${tab.key}`" :key="tab.key" class="tab" :class="{active:activeTab===tab.key}" role="tab" :aria-selected="activeTab===tab.key" :aria-controls="`measured-panel-${activeTab}`" :tabindex="activeTab===tab.key ? 0 : -1" @click="selectTab(tab.key)">{{ tab.label }}</button></div>
            <div :id="`measured-panel-${activeTab}`" class="measured-tab-panel" role="tabpanel" :aria-labelledby="`measured-tab-${activeTab}`">
            <ResultOverview :read-only="readOnly" v-if="activeTab==='overview'" :key="selected.id" source-kind="measured" :cell-line="selected.cell_line" :perturbation="selected.perturbation" :counts="summary.counts" :gene-count="summary.gene_count" :source-label="sourceLabel" :expression-units="summary.expression_units" :genes="overviewGenes" :tasks="overviewTaskRows" @select-gene="selectFeature('gene',$event)" @select-task="selectFeature('task',$event)" @interpret="selectedFeature={view:'overview'}; openAssistant(false)" @focus-task="focusedTask=$event"><template #landscape><ResearchCanvas kind="measured" :record-id="selected.id" :tasks="overviewTaskRows" :knowledge-version="summary.metabolism.database_version" @selection="canvasSelection=$event" @select-task="selectFeature('task',$event)" /></template></ResultOverview>
            <p v-if="overviewLoading && ['overview','metabolism'].includes(activeTab)" role="status">正在读取完整任务评分…</p>
            <p v-if="overviewError && ['overview','metabolism'].includes(activeTab)" class="notice notice-danger" role="alert">任务概览读取失败：{{ overviewError }} <button class="btn btn-sm" @click="overviewRefresh++">重试</button></p>
            <div v-if="selectedFeature.feature_id" class="btn-row"><span class="muted">当前选中：{{ selectedFeatureLabel() }}<small v-if="selectedFeature.feature_kind==='task'" class="selected-feature-id"> {{ selectedFeature.feature_id }}</small></span><button v-if="!readOnly" class="btn btn-sm" @click="openAssistant(false)">解读选中指标</button><button class="btn btn-sm" @click="clearFeature">清除指标选择</button></div>
            <section v-if="activeTab==='comparison'" class="card measured-comparison-card">
              <span class="eyebrow">OBSERVED GROUP COMPARISON</span>
              <div class="section-heading"><div><h2>实测群体对照</h2><p class="muted">两组均来自实测 RNA；当前视图不包含模型预测或独立泛化检验。</p></div><span class="comparison-identity-tag">对照 ↔ 扰动实测</span></div>
              <div class="count-grid"><div><span>实测对照</span><strong>{{ numeric(summary.counts.control) }}</strong><small>个细胞</small></div><div><span>实测扰动</span><strong>{{ numeric(summary.counts.observed) }}</strong><small>个细胞</small></div><div><span>共同基因</span><strong>{{ numeric(summary.gene_count) }}</strong><small>完整共同面板</small></div></div>
              <p class="count-note">匹配前：对照 {{ numeric(summary.input_counts.control) }} / 扰动 {{ numeric(summary.input_counts.observed) }}；匹配后：对照 {{ numeric(summary.counts.control) }} / 扰动 {{ numeric(summary.counts.observed) }}。{{ imported ? '自有数据中的' : '固定源中的' }}扰动细胞总数：{{ numeric(summary.source_cell_count) }}。</p>
              <details><summary>采样与批次匹配详情</summary><dl class="detail-list"><template v-for="[key, value] in batchDetails" :key="key"><dt>{{ key }}</dt><dd>{{ detailValue(value) }}</dd></template></dl><p v-if="!batchDetails.length" class="muted">本次摘要未提供额外匹配详情。</p></details>
              <ul v-if="summary.warnings.length" class="warning-list"><li v-for="warning in summary.warnings" :key="warning">{{ warning }}</li></ul>
              <div class="comparison-data-heading"><h3>主要基因响应的同尺比较</h3><button class="btn btn-sm" @click="selectTab('genes')">查看完整表达 <UiIcon name="arrow" :size="13"/></button></div><p class="table-unit">{{ summary.expression_units }} · 差值 = 实测扰动均值 − 实测对照均值；方向不等于统计显著性。</p><div v-if="summary.top_genes.length" class="table-wrap"><table class="result-table"><thead><tr><th>基因</th><th>实测对照均值</th><th>实测扰动均值</th><th>差值</th></tr></thead><tbody><tr v-for="row in summary.top_genes" :key="rowId(row)"><td><button class="comparison-gene" @click="selectFeature('gene', rowId(row))">{{ rowId(row) }}</button></td><td>{{ numeric(row.control) }}</td><td>{{ numeric(row.observed) }}</td><td :class="{ 'delta-positive':(row.observed_delta ?? 0)>0, 'delta-negative':(row.observed_delta ?? 0)<0 }">{{ numeric(row.observed_delta) }}</td></tr></tbody></table></div><p v-else class="empty-section">摘要未提供主要基因列表，请在表达响应中查看完整结果表。</p>
            </section>
            <section v-if="activeTab==='genes'" class="card measured-projection-card"><span class="eyebrow">EXPRESSION RESPONSE</span>
              <div v-if="projectionOpen" class="section-heading"><div><h2>单细胞表达投影</h2><p class="muted">{{ projection?.method || (embedding === 'pca' ? '对照参考 PCA' : '共同表达空间 UMAP') }}</p></div><div class="btn-row"><button class="btn btn-sm" :aria-pressed="embedding === 'pca'" @click="embedding = 'pca'">PCA</button><button class="btn btn-sm" :aria-pressed="embedding === 'umap'" @click="embedding = 'umap'">UMAP</button><button class="btn btn-sm" :disabled="!!downloading || !summary.projections.pca.available" @click="download('projection')">投影 JSON</button></div></div>
              <template v-if="projectionOpen"><p v-if="!projectionAvailable" class="empty-section">本次未生成 {{ embedding.toUpperCase() }} 投影：{{ summary.projections[embedding].reason || '未提供可核验的投影产物' }}。表达结果仍可查看与下载。</p><p v-else-if="projectionLoading" role="status">正在读取实测细胞投影…</p><div v-else-if="projectionError" class="notice notice-danger" role="alert">{{ projectionError }} <button class="btn btn-sm" @click="projectionRefresh++">重新读取投影</button></div><p v-else-if="!projection?.points.length" class="empty-section">投影没有可显示的细胞坐标。</p><MeasuredProjection v-else :data="projection" :embedding="embedding" :analysis-id="selected.id" @selection="expressionSelection=$event"/></template>
            </section>
            <section v-if="activeTab==='metabolism'" class="card function-context"><div><span class="eyebrow">FUNCTIONAL EVIDENCE</span><h2>从表达支持，核查功能线索</h2><p>代谢任务与反应评分由当前实测表达推断。查看成员覆盖、分数方向和计算来源，保留缺失信息。</p></div><div class="function-readiness"><span class="status-tag" :class="metabolismAvailable ? 'completed' : 'interrupted'">{{ metabolismAvailable ? '功能结果已提供' : '功能结果不可用' }}</span><p v-if="metabolismAvailable">{{ summary.metabolism.task_count ?? '—' }} 个任务 · {{ summary.metabolism.reaction_count ?? '—' }} 个反应</p><p v-else>{{ summary.metabolism.reason || '本次未生成可核验的代谢评分产物' }}</p><small>{{ summary.metabolism.database_version || '数据库版本见来源清单' }}</small></div></section>
            <div v-if="activeTab==='metabolism' && activeEvidenceTask && metabolismAvailable" ref="taskEvidenceSection" class="measured-task-evidence-anchor"><MeasuredTaskEvidence :analysis-id="selected.id" :task-id="activeEvidenceTask" @select-gene="selectFeature('gene',$event)" /></div>
            <section v-if="['genes','metabolism'].includes(activeTab)" ref="tableSection" class="card measured-data-card" style="scroll-margin-top:90px">
              <div class="section-heading"><h2>{{ activeTab==='genes' ? '基因表达响应' : '任务与反应评分' }}</h2><button v-if="!readOnly" class="btn btn-sm" :disabled="!!downloading || (tableKind !== 'genes' && !metabolismAvailable)" @click="download(tableKind)">{{ downloading === tableKind ? '正在下载…' : '完整表 CSV' }}</button></div>
              <div v-if="activeTab==='metabolism'" class="table-tabs" role="group" aria-label="选择功能结果表"><button v-for="item in (['tasks', 'reactions'] as const)" :key="item" class="btn btn-sm" :aria-pressed="tableKind === item" @click="changeKind(item)">{{ { tasks: '代谢任务', reactions: '反应评分' }[item] }}</button></div>
              <p class="table-unit">单位：{{ units || '未提供' }}。{{ tableKind === 'genes' ? '表达值为 mean(log1p(CP10K))。' : '代谢评分由实测表达推断，不代表实测通量、代谢物浓度或酶活性。' }}</p>
              <template v-if="tableKind === 'genes' || metabolismAvailable">
                <form class="table-search" @submit.prevent="searchTable"><label for="measured-table-search" class="sr-only">检索当前结果表</label><input id="measured-table-search" v-model="tableSearch" class="input" placeholder="检索基因、任务或反应" maxlength="500"/><button class="btn" type="submit">检索</button></form>
                <p v-if="tableLoading" role="status">正在读取结果表…</p><div v-else-if="tableError" class="notice notice-danger" role="alert">{{ tableError }} <button class="btn btn-sm" @click="tableRefresh++">重新读取结果表</button></div><p v-else-if="!table?.items.length" class="empty-section">没有符合条件的结果。</p>
                <div v-else class="table-wrap"><table class="result-table"><thead><tr><th scope="col">{{ tableKind === 'genes' ? '基因' : tableKind === 'tasks' ? '任务' : '反应' }}</th><th scope="col">实测对照均值</th><th scope="col">实测扰动均值</th><th scope="col">差值（扰动 − 对照）</th><th v-if="tableKind === 'tasks'" scope="col">基因覆盖比例</th></tr></thead><tbody><tr v-for="row in table.items" :key="rowId(row)" :class="{ 'is-selected': selectedFeature.feature_id === rowId(row) }"><td><button v-if="tableKind!=='reactions'" class="comparison-gene" :aria-pressed="selectedFeature.feature_id === rowId(row)" @click="focusRow(row)">{{ rowLabel(row) }}</button><strong v-else>{{ rowId(row) }}</strong><small v-if="row.task" class="task-original-id">{{ rowId(row) }}</small><small v-else-if="row.label && row.label !== rowId(row)">{{ row.label }}</small></td><td>{{ numeric(row.control) }}</td><td>{{ numeric(row.observed) }}</td><td :class="{ 'delta-positive': (row.observed_delta ?? 0) > 0, 'delta-negative': (row.observed_delta ?? 0) < 0 }">{{ numeric(row.observed_delta) }}</td><td v-if="tableKind === 'tasks'">{{ row.gene_fraction == null ? '—' : `${numeric(row.gene_fraction * 100)}%` }}</td></tr></tbody></table></div>
                <footer v-if="table" class="pagination"><span>共 {{ table.total }} 条 · 第 {{ tablePage }} / {{ tablePages }} 页</span><div class="btn-row"><button class="btn btn-sm" :disabled="tablePage <= 1 || tableLoading" @click="tablePage--">上一页</button><button class="btn btn-sm" :disabled="tablePage >= tablePages || tableLoading" @click="tablePage++">下一页</button></div></footer>
              </template><p v-else class="empty-section">代谢分析不可用：{{ summary.metabolism.reason || '未生成可核验的代谢评分产物' }}。实测表达比较仍然可用。</p>
            </section>
            </div>
            <details class="card measured-provenance"><summary>完整来源、采样说明与解释边界</summary>
              <div class="section-heading"><h2>数据来源与解释边界</h2><span class="comparison-identity-tag">{{ sourceLabel }}</span></div>
              <p class="muted">实测 RNA 的组间差异是数据中的观察结果。代谢任务与反应评分是表达推断结果；本分析不证明模型的独立泛化能力或因果机制。</p>
              <p v-if="summary.metabolism.available" class="muted">代谢数据库 {{ summary.metabolism.database_version || '版本见来源清单' }} · {{ summary.metabolism.task_count ?? '—' }} 个任务 · {{ summary.metabolism.reaction_count ?? '—' }} 个反应</p>
              <ul v-if="summary.limitations?.length" class="warning-list"><li v-for="limit in summary.limitations" :key="limit">{{ limit }}</li></ul>
              <details><summary>查看来源与可追溯信息</summary><dl class="detail-list"><template v-for="[key, value] in provenanceDetails" :key="key"><dt>{{ key }}</dt><dd>{{ detailValue(value) }}</dd></template></dl><p v-if="!provenanceDetails.length" class="muted">本次摘要未提供额外来源详情，请核对完整结果包。</p></details>
            </details>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.analysis-layout.result-layout{grid-template-columns:minmax(0,1fr)}
.analysis-layout{display:grid;grid-template-columns:280px minmax(0,1fr);gap:22px;align-items:start}.card{padding:24px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius)}.selector-panel{position:sticky;top:90px}.card h2{font-size:18px;font-weight:500;margin:0 0 12px}.muted,.card small,.count-note,.table-unit{color:var(--muted);font-size:12px;line-height:1.8}.selector-form{display:grid;gap:18px;margin-top:24px}.selector-form .label{font-size:12px;margin-bottom:8px}.selector-form .input,.selector-form .select{min-height:40px;font-size:12px;width:100%}.selector-form small{display:block;margin-top:6px;font-size:11px}.coverage-state{padding:14px;background:var(--surface-soft);border-left:2px solid var(--border-strong);font-size:12px;line-height:1.8;color:var(--muted)}.coverage-state span{display:block}.coverage-state strong{color:var(--primary);font-weight:500}.selector-links{display:grid;gap:12px;border-top:1px solid var(--border);margin-top:24px;padding-top:20px;font-size:12px;color:var(--primary)}.selector-links small{font-size:11px}.analysis-content{display:grid;gap:20px;min-width:0}.section-heading{display:flex;justify-content:space-between;align-items:start;gap:16px;margin-bottom:18px}.section-heading p{margin:0}.section-heading h2{margin-bottom:8px}.status-tag{padding:5px 9px;font-size:11px;white-space:nowrap;background:var(--surface-tint);color:var(--primary);border-radius:3px}.status-tag.completed{color:var(--ok);background:var(--ok-bg)}.status-tag.failed,.status-tag.interrupted{color:var(--danger);background:var(--danger-bg)}.status-card progress{width:100%;height:7px;accent-color:var(--primary)}.status-card>p{font-size:13px;line-height:1.8}.empty-state{min-height:340px;padding:55px 40px;display:flex;flex-direction:column;justify-content:center;align-items:start}.empty-state h2{font-size:26px;margin-top:18px}.empty-state p{max-width:660px;color:var(--muted);font-size:13px;line-height:1.9}.count-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border-top:1px solid var(--border);border-bottom:1px solid var(--border);margin:20px 0}.count-grid>div{padding:20px;border-right:1px solid var(--border)}.count-grid>div:first-child{padding-left:0}.count-grid>div:last-child{border:0}.count-grid span,.count-grid small{display:block;font-size:11px;color:var(--muted)}.count-grid strong{display:block;font-weight:500;font-size:30px;color:var(--ink);margin:9px 0;font-variant-numeric:tabular-nums}details{margin-top:18px;font-size:12px}summary{cursor:pointer;color:var(--primary);line-height:1.8}.detail-list{display:grid;grid-template-columns:minmax(120px,1fr) minmax(0,3fr);gap:12px;border-top:1px solid var(--border);padding-top:18px;line-height:1.7}.detail-list dt{color:var(--muted);overflow-wrap:anywhere}.detail-list dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--ink)}.warning-list{padding:14px 14px 14px 30px;background:var(--surface-soft);font-size:12px;line-height:1.8;color:var(--muted)}.table-tabs{display:flex;gap:7px;margin-bottom:15px}.btn[aria-pressed=true]{border-color:var(--primary);color:var(--primary);background:var(--primary-weak)}.table-search{display:flex;gap:10px;margin:20px 0}.table-search .input{max-width:360px;min-height:38px;font-size:12px}.table-wrap{overflow:auto}.result-table{width:100%;border-collapse:collapse;font-size:12px;text-align:left}.result-table th{font-size:11px;color:var(--muted);background:var(--table-head-bg);font-weight:500;white-space:nowrap}.result-table th,.result-table td{padding:14px 12px;border-bottom:1px solid var(--border)}.result-table td:not(:first-child){font-variant-numeric:tabular-nums}.result-table td strong{font-weight:500}.result-table small{display:block;max-width:250px;font-size:10px;margin-top:5px}.delta-positive{color:var(--delta-up,#b26b4d)}.delta-negative{color:var(--primary)}.pagination{display:flex;justify-content:space-between;align-items:center;gap:15px;margin-top:20px;font-size:11px;color:var(--muted)}.empty-section{padding:30px 10px;color:var(--muted);font-size:13px;line-height:1.9}.history-panel{margin-top:28px}.history-table td{padding:18px 12px}.notice{font-size:12px;line-height:1.8}.notice p{margin:0 0 10px}.eyebrow{font-size:10px;letter-spacing:.12em}.measured-page .btn-row{flex-wrap:wrap}.measured-page .btn{font-size:12px}.history-table a:not(.btn){color:var(--primary)}
@media(max-width:1279px){.analysis-layout{grid-template-columns:250px minmax(0,1fr);gap:16px}.card{padding:20px}.result-table th,.result-table td{padding:12px 8px}}@media(max-width:900px){.analysis-layout{grid-template-columns:1fr}.selector-panel{position:static}.selector-form{grid-template-columns:1fr 1fr}.coverage-state{grid-column:1/-1}.section-heading{flex-wrap:wrap}}

.measured-page{max-width:1440px}.result-breadcrumb{display:flex;align-items:center;gap:10px;font-size:10px;color:var(--muted);margin:0 0 20px}.result-breadcrumb a{color:var(--muted);text-decoration:none}.result-breadcrumb strong{font-weight:500;color:var(--primary)}.analysis-content{gap:17px}.status-card{border-radius:16px;position:relative;overflow:visible}.result-identity-heading{margin-bottom:0;align-items:flex-start}.result-identity-heading h1{font-size:29px;font-weight:500;line-height:1.5;margin:10px 0 9px}.result-identity-heading .status-tag{font-size:10px;vertical-align:middle;margin-left:11px;font-weight:400;border-radius:5px}.result-identity-heading .identity-divider{font-weight:300;color:var(--border-strong);margin:0 4px}.result-identity-heading small{font-size:11px}.result-identity{font-size:9px!important;color:var(--faint)!important;margin:8px 0 0!important}.result-primary-actions{gap:8px;padding-top:4px;flex:none;align-items:center}.result-action-menu{position:relative;z-index:21;margin:0;text-align:left}.result-action-menu>summary{cursor:pointer;list-style:none;white-space:nowrap;display:flex;gap:7px}.result-action-menu>summary::-webkit-details-marker{display:none}.result-action-menu[open]>summary{background:var(--primary-weak);border-color:var(--primary);color:var(--primary)}.result-action-popover{position:absolute;right:0;top:calc(100% + 8px);width:270px;max-width:calc(100vw - 40px);border:1px solid var(--border);border-radius:13px;background:var(--card);box-shadow:var(--shadow-lg);padding:15px}.action-menu-label{display:block;font-size:10px;color:var(--faint);margin:1px 7px 8px}.result-menu-item{display:flex;align-items:center;gap:10px;width:100%;padding:11px 8px;background:transparent;border:0;border-radius:7px;color:var(--ink);font:12px var(--font);text-decoration:none;cursor:pointer;text-align:left}.result-menu-item:hover{background:var(--table-row-hover)}.result-menu-item>svg{color:var(--primary);flex:none}.action-menu-divider{border-top:1px solid var(--border);margin:9px 0 13px}.status-card>progress{margin-top:20px}.status-card>p{margin-top:17px}.result-tabs{gap:28px!important;display:flex;flex-wrap:nowrap;overflow-x:auto;border-bottom:1px solid var(--border);background:none;padding:0 2px;margin:0}.result-tabs .tab{padding:13px 0!important;border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent;color:var(--muted);font-size:13px!important;white-space:nowrap}.result-tabs .tab.active{background:transparent;color:var(--primary-strong);border-bottom-color:var(--primary);font-weight:500}.measured-tab-panel{display:grid;gap:19px;min-width:0}.measured-tab-panel :deep(.research-canvas){margin-bottom:0}.measured-tab-panel :deep(.result-overview){margin-bottom:0;border-radius:15px}.measured-tab-panel :deep(.overview-heading){padding:20px 24px 16px}.measured-tab-panel :deep(.overview-heading h2){display:none}.measured-tab-panel :deep(.overview-heading .eyebrow){font-size:12px;margin-bottom:7px;color:var(--ink);font-weight:500}.measured-tab-panel :deep(.overview-subtitle){font-size:11px;margin-top:0}.measured-tab-panel .card{border-radius:15px}.measured-projection-card>.eyebrow,.measured-comparison-card>.eyebrow{display:block;color:var(--faint);font-size:9px;margin-bottom:15px}.measured-projection-card .section-heading h2,.measured-comparison-card .section-heading h2{font-size:21px;margin-bottom:9px}.measured-projection-card .section-heading p,.measured-comparison-card .section-heading p{font-size:11px!important}.comparison-identity-tag{font-size:10px;white-space:nowrap;background:var(--primary-weak);color:var(--primary);border-radius:5px;padding:6px 9px}.count-grid{border:1px solid var(--border);border-radius:12px;background:var(--card-soft);overflow:hidden}.count-grid>div:first-child{padding-left:20px}.count-grid strong{font:29px Bahnschrift,sans-serif;color:var(--primary-strong)}.count-grid>div{padding:20px 25px}.count-grid span,.count-grid small{font-size:10px}.count-note{font-size:11px;line-height:1.9}.comparison-data-heading{display:flex;align-items:center;justify-content:space-between;gap:15px;margin-top:25px}.comparison-data-heading h3{font-size:15px;font-weight:500;margin:0}.comparison-gene{display:inline-block;font:inherit;font-weight:500;color:var(--primary);text-align:left;background:none;border:0;cursor:pointer;padding:0;text-decoration:underline;text-underline-offset:4px;text-decoration-color:var(--border-strong)}.comparison-gene:hover{color:var(--primary-strong);text-decoration-color:var(--primary)}.result-table tr.is-selected{background:var(--table-row-selected)}.result-table tr:hover{background:var(--table-row-hover)}.function-context{display:grid;grid-template-columns:1fr minmax(200px,.55fr);align-items:center;gap:25px;background:linear-gradient(115deg,var(--card),var(--card-soft))}.function-context .eyebrow{color:var(--faint);font-size:9px}.function-context h2{font-size:22px;margin:12px 0}.function-context p{font-size:12px;line-height:1.9;color:var(--muted);margin:0;max-width:610px}.function-readiness{border-left:1px solid var(--border);padding-left:25px}.function-readiness p{font-size:11px;margin:12px 0 6px}.function-readiness small{font-size:10px}.measured-data-card .section-heading{align-items:center}.measured-data-card h2{margin-bottom:0;font-size:20px}.table-unit{font-size:11px;line-height:1.9;padding:12px 14px;background:var(--card-soft);border-radius:8px;margin:14px 0}.table-tabs{gap:8px}.table-tabs .btn{font-size:11px!important}.table-search .input{border-radius:8px;font-size:12px}.result-table th{font-size:10px;padding:13px}.result-table td{font-size:12px}.result-table small{font-size:10px}.measured-provenance{margin-top:3px;border-radius:13px!important;padding:0!important}.measured-provenance>summary{padding:16px 22px;font-size:12px}.measured-provenance[open]{padding:0 22px 21px!important}.measured-provenance[open]>summary{margin:0 -22px 22px;border-bottom:1px solid var(--border)}.measured-provenance .section-heading h2{font-size:18px}.measured-provenance .muted{font-size:11px!important}.warning-list{border-radius:8px;font-size:11px}.detail-list{font-size:11px}.analysis-content>.notice{border-radius:10px}.analysis-content :deep(.research-evidence-actions){padding:0 2px}.status-card>.btn-row{margin-top:14px}
@media(max-width:1050px){.result-identity-heading{flex-direction:column;gap:14px}.result-identity-heading h1{font-size:27px}.result-primary-actions{padding-top:0}.result-action-popover{right:auto;left:0}.function-context{grid-template-columns:1fr}.function-readiness{border-left:0;border-top:1px solid var(--border);padding:18px 0 0}.function-readiness p{display:inline-block;margin:0 15px}.function-readiness small{display:block;margin-top:10px}}@media(max-width:650px){.result-breadcrumb{font-size:9px;margin-bottom:15px}.status-card{padding:20px!important}.result-identity-heading h1{font-size:24px;overflow-wrap:anywhere}.result-identity-heading .status-tag{font-size:9px;margin-left:5px}.result-identity-heading small{font-size:10px}.result-primary-actions .btn{font-size:10px!important;padding:8px 10px!important}.result-action-popover{left:auto;right:0}.analysis-content{gap:15px}.result-tabs{gap:22px!important}.result-tabs .tab{font-size:12px!important}.measured-tab-panel{gap:15px}.measured-tab-panel .card{padding:20px!important}.measured-tab-panel :deep(.overview-heading){padding:18px}.measured-tab-panel :deep(.overview-subtitle){font-size:10px}.measured-tab-panel :deep(.interpret-button){font-size:10px;padding:8px 10px}.measured-tab-panel :deep(.population-counts){font-size:10px;padding:0 18px 16px}.count-grid>div{padding:15px 12px}.count-grid>div:first-child{padding-left:12px}.count-grid strong{font-size:24px}.count-grid span,.count-grid small{font-size:9px}.count-note{font-size:10px}.comparison-data-heading{align-items:flex-start}.comparison-data-heading h3{font-size:14px;line-height:1.8}.comparison-data-heading .btn{font-size:10px!important;white-space:nowrap}.table-unit{font-size:10px;padding:11px}.function-context h2{font-size:20px}.function-context p{font-size:11px}.function-readiness p{display:block;margin:10px 0 6px}.measured-data-card h2{font-size:18px}.measured-data-card .section-heading>.btn{font-size:10px!important}.result-table{min-width:580px}.table-search .input{min-width:0;flex:1}.pagination{font-size:10px;flex-wrap:wrap}.pagination .btn{font-size:10px!important}.detail-list{grid-template-columns:1fr;gap:7px;font-size:10px}.detail-list dd{margin-bottom:8px}.measured-provenance>summary{font-size:11px;padding:15px 19px}.measured-provenance[open]{padding:0 19px 19px!important}.measured-provenance[open]>summary{margin-left:-19px;margin-right:-19px}.measured-provenance .section-heading{gap:12px}.measured-provenance .section-heading h2{font-size:17px}}
.measured-task-evidence-anchor{scroll-margin-top:90px;margin:18px 0}.selected-feature-id,.task-original-id{display:block;font-size:12px;line-height:1.6;overflow-wrap:anywhere;color:var(--muted)}
</style>
