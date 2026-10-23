<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { measuredApi } from '../api/measured'
import { ApiError } from '../api/http'
import MeasuredProjection from '../components/MeasuredProjection.vue'
import ResultOverview from '../components/ResultOverview.vue'
import { useAssistantSource, openAssistant } from '../stores/assistantSource'
import { taskName } from '../utils/biologyLocale'
import type { AssistantSelection } from '../api/assistant'
import { downloadBlob } from '../utils/csv'
import { fmtServerTime } from '../utils/format'
import type { MeasuredAnalysis, MeasuredDownloadKind, MeasuredProjection as Projection, MeasuredRequest, MeasuredRow, MeasuredStatus, MeasuredTable, MeasuredTableKind } from '../types/measured'

const route = useRoute(), router = useRouter()
const labels: Record<MeasuredStatus, string> = { queued: '等待分析', preparing: '准备实测数据', analysing: '分析中', completed: '已完成', failed: '分析失败', cancelled: '已取消', interrupted: '分析中断' }
const selected = ref<MeasuredAnalysis | null>(null), recordLoading = ref(false), recordError = ref('')
const submitting = ref(false), cancelling = ref(false), actionError = ref(''), uncertain = ref(false)
const projectionOpen = ref(false), tableOpen = ref(false)
const tableSection = ref<HTMLDetailsElement | null>(null)
const overviewTasks = ref<MeasuredRow[]>([]), overviewError = ref(''), overviewLoading = ref(false), overviewRefresh = ref(0)
const selectedFeature = ref<AssistantSelection>({view:'overview'})
const tableKind = ref<MeasuredTableKind>('genes'), tableSearch = ref(''), appliedSearch = ref(''), tablePage = ref(1), table = ref<MeasuredTable | null>(null), tableLoading = ref(false), tableError = ref('')
const embedding = ref<'pca' | 'umap'>('pca'), projection = ref<Projection | null>(null), projectionLoading = ref(false), projectionError = ref('')
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
useAssistantSource(() => selected.value ? {
  kind:'measured', id:selected.value.id, title:`${selected.value.cell_line} · ${selected.value.perturbation}`,
  completed:selected.value.status === 'completed', view:selectedFeature.value.view, selection:selectedFeature.value,
} : null)
const overviewGenes = computed(() => (summary.value?.top_genes ?? []).map(row => ({id:row.gene ?? '', control:row.control, observed:row.observed, delta:row.observed_delta})))
const overviewTaskRows = computed(() => overviewTasks.value.map(row => ({id:row.task ?? '', label:taskName(row.task ?? '', row.label), control:row.control, observed:row.observed, delta:row.observed_delta, coverage:row.gene_fraction})))
function selectFeature(kind:'gene'|'task', id:string) {
  selectedFeature.value = {view:kind === 'gene' ? 'genes' : 'metabolism', feature_kind:kind, feature_id:id}
  tableKind.value = kind === 'gene' ? 'genes' : 'tasks'; tableSearch.value = id; appliedSearch.value = id; tablePage.value = 1; tableOpen.value = true
  void nextTick(() => tableSection.value?.scrollIntoView({block:'start', behavior:'smooth'}))
}
function isActive(status: MeasuredStatus) { return ['queued', 'preparing', 'analysing'].includes(status) }
function errorText(error: unknown) { return error instanceof Error ? error.message : '读取失败，请重试' }
function numeric(value: number | null | undefined) { return value == null || !Number.isFinite(value) ? '—' : value.toLocaleString('zh-CN', { maximumFractionDigits: 5 }) }
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
  clearPolling(); selected.value = null; recordError.value = ''; recordLoading.value = false
  selectedFeature.value = {view:'overview'}; projectionOpen.value = false; tableOpen.value = false
  tableKind.value = 'genes'; tablePage.value = 1; tableSearch.value = ''; appliedSearch.value = ''; embedding.value = 'pca'
  if (id) void loadRecord(id)
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
function retry() { if (selected.value) void start({ cell_line: selected.value.cell_line, perturbation: selected.value.perturbation, max_cells: selected.value.max_cells, seed: selected.value.seed }) }

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
function searchTable() { appliedSearch.value = tableSearch.value.trim(); tablePage.value = 1 }
function changeKind(kind: MeasuredTableKind) { selectedFeature.value = {view:kind==='genes'?'genes':'metabolism'}; tableKind.value = kind; tablePage.value = 1; tableSearch.value = ''; appliedSearch.value = '' }
async function download(kind: MeasuredDownloadKind) {
  if (!selected.value || downloading.value) return
  downloading.value = kind; actionError.value = ''
  try { const file = await measuredApi.download(selected.value.id, kind, lifetime.signal); if (!lifetime.signal.aborted) downloadBlob(file.blob, file.filename) }
  catch (error) { if (!lifetime.signal.aborted) actionError.value = errorText(error) }
  finally { if (!lifetime.signal.aborted) downloading.value = null }
}
onBeforeUnmount(() => { lifetime.abort(); clearPolling() })
</script>

<template>
  <div class="page measured-page">
    <header class="page-heading"><div><span class="eyebrow">MEASURED PERTURBATION ANALYSIS</span><h1>实测结果解读</h1><p>比较公开 Perturb-seq 中的实测对照与实测扰动，查看表达变化与代谢任务评分。</p></div><RouterLink to="/research?type=measured" class="btn">新建实测分析</RouterLink></header>
    <div class="analysis-layout result-layout">
      <div class="analysis-content">
        <div v-if="actionError" class="notice notice-danger" role="alert">{{ actionError }}</div>
        <div v-if="uncertain" class="notice" role="alert"><p>提交结果待确认，请先核对实验记录，避免重复创建。页面不会自动重发请求。</p><div class="btn-row"><RouterLink to="/records?category=measured" class="btn btn-sm">核对实测记录</RouterLink><button class="btn btn-sm" @click="uncertain = false">已核对记录，允许再次提交</button></div></div>
        <section v-if="recordError" class="card empty-state" role="alert"><h2>分析记录读取失败</h2><p>{{ recordError }}</p><button class="btn" @click="loadRecord()">重新读取</button></section>
        <section v-else-if="recordLoading && !selected" class="card empty-state" role="status">正在读取分析记录…</section>
        <section v-else-if="!selected" class="card empty-state"><span class="eyebrow">OBSERVED EXPRESSION</span><h2>从真实扰动数据开始</h2><p>选择细胞背景和扰动基因，明确启动分析后生成结果。完整共同基因面板用于表达比较，不限定为模型的 2,000 个高变基因。</p><p>结果包含实测组均值、扰动减对照的差值，以及可用的投影与表达推断代谢评分。</p></section>
        <template v-if="selected">
          <section class="card status-card" aria-live="polite">
            <div class="section-heading"><div><span class="eyebrow">MEASURED DATA · 实测数据</span><h2>{{ selected.cell_line }} / {{ selected.perturbation }}</h2><small>{{ fmtServerTime(selected.created_at) }} · 目标实测上限 {{ selected.max_cells }} · 种子 {{ selected.seed }}</small></div><span class="status-tag" :class="selected.status">{{ labels[selected.status] }}</span></div>
            <template v-if="active"><progress :value="progress" max="100" :aria-label="`分析进度 ${progress}%`"/><p>{{ selected.message || '分析任务已接收' }} · {{ numeric(progress) }}%</p><div class="btn-row"><button class="btn" :disabled="cancelling" @click="cancel">{{ cancelling ? '正在取消…' : '取消分析' }}</button><small>离开本页后，后台分析仍会继续。</small></div></template>
            <template v-else-if="selected.status !== 'completed'"><p role="status">{{ selected.error_message || selected.message || '本次分析没有可用结果。可以重新创建一次分析。' }}</p><button class="btn" :disabled="submitting || uncertain" @click="retry">重新分析</button></template>
            <p v-else-if="!summary" class="notice">记录已完成，但没有可读取的结果摘要。<button class="btn btn-sm" @click="loadRecord()">重新读取</button></p>
          </section>
          <template v-if="summary">
            <ResultOverview :key="selected.id" source-kind="measured" :cell-line="selected.cell_line" :perturbation="selected.perturbation" :counts="summary.counts" :genes="overviewGenes" :tasks="overviewTaskRows" @select-gene="selectFeature('gene',$event)" @select-task="selectFeature('task',$event)" @interpret="selectedFeature={view:'overview'}; openAssistant(false)" />
            <p v-if="overviewLoading" role="status">正在读取完整任务评分…</p>
            <p v-if="overviewError" class="notice notice-danger" role="alert">任务概览读取失败：{{ overviewError }} <button class="btn btn-sm" @click="overviewRefresh++">重试</button></p>
            <div v-if="selectedFeature.feature_id" class="btn-row"><span class="muted">当前选中：{{ selectedFeature.feature_id }}</span><button class="btn btn-sm" @click="openAssistant(false)">解读选中指标</button><button class="btn btn-sm" @click="selectedFeature={view:'overview'}">返回整体解读</button></div>
            <details class="card"><summary>分析规模、采样与完整结果下载</summary>
              <div class="section-heading"><div><h2>实际分析规模</h2><p class="muted">两组均来自实测 RNA；差值 = 实测扰动均值 − 实测对照均值。</p></div><button class="btn btn-primary" :disabled="!!downloading" @click="download('bundle')">{{ downloading === 'bundle' ? '正在下载…' : '完整结果 ZIP' }}</button></div>
              <div class="count-grid"><div><span>实测对照</span><strong>{{ numeric(summary.counts.control) }}</strong><small>个细胞</small></div><div><span>实测扰动</span><strong>{{ numeric(summary.counts.observed) }}</strong><small>个细胞</small></div><div><span>共同基因</span><strong>{{ numeric(summary.gene_count) }}</strong><small>完整共同面板</small></div></div>
              <p class="count-note">匹配前：对照 {{ numeric(summary.input_counts.control) }} / 扰动 {{ numeric(summary.input_counts.observed) }}；匹配后：对照 {{ numeric(summary.counts.control) }} / 扰动 {{ numeric(summary.counts.observed) }}。固定源中的扰动细胞总数：{{ numeric(summary.source_cell_count) }}。</p>
              <details><summary>采样与批次匹配详情</summary><dl class="detail-list"><template v-for="[key, value] in batchDetails" :key="key"><dt>{{ key }}</dt><dd>{{ detailValue(value) }}</dd></template></dl><p v-if="!batchDetails.length" class="muted">本次摘要未提供额外匹配详情。</p></details>
              <ul v-if="summary.warnings.length" class="warning-list"><li v-for="warning in summary.warnings" :key="warning">{{ warning }}</li></ul>
            </details>
            <details class="card" @toggle="projectionOpen=($event.target as HTMLDetailsElement).open"><summary>专业检查：单细胞表达投影（PCA / UMAP）</summary>
              <div v-if="projectionOpen" class="section-heading"><div><h2>单细胞表达投影</h2><p class="muted">{{ projection?.method || (embedding === 'pca' ? '对照参考 PCA' : '共同表达空间 UMAP') }}</p></div><div class="btn-row"><button class="btn btn-sm" :aria-pressed="embedding === 'pca'" @click="embedding = 'pca'">PCA</button><button class="btn btn-sm" :aria-pressed="embedding === 'umap'" @click="embedding = 'umap'">UMAP</button><button class="btn btn-sm" :disabled="!!downloading || !summary.projections.pca.available" @click="download('projection')">投影 JSON</button></div></div>
              <template v-if="projectionOpen"><p v-if="!projectionAvailable" class="empty-section">本次未生成 {{ embedding.toUpperCase() }} 投影：{{ summary.projections[embedding].reason || '未提供可核验的投影产物' }}。表达结果仍可查看与下载。</p><p v-else-if="projectionLoading" role="status">正在读取实测细胞投影…</p><div v-else-if="projectionError" class="notice notice-danger" role="alert">{{ projectionError }} <button class="btn btn-sm" @click="projectionRefresh++">重新读取投影</button></div><p v-else-if="!projection?.points.length" class="empty-section">投影没有可显示的细胞坐标。</p><MeasuredProjection v-else :data="projection" :embedding="embedding" :analysis-id="selected.id"/></template>
            </details>
            <details ref="tableSection" class="card" :open="tableOpen" @toggle="tableOpen=($event.target as HTMLDetailsElement).open" style="scroll-margin-top:90px"><summary>详细数据：表达与代谢评分</summary>
              <div class="section-heading"><h2>表达与代谢评分</h2><button class="btn btn-sm" :disabled="!!downloading || (tableKind !== 'genes' && !metabolismAvailable)" @click="download(tableKind)">{{ downloading === tableKind ? '正在下载…' : '完整表 CSV' }}</button></div>
              <div class="table-tabs" role="group" aria-label="选择结果表"><button v-for="item in (['genes', 'tasks', 'reactions'] as const)" :key="item" class="btn btn-sm" :aria-pressed="tableKind === item" @click="changeKind(item)">{{ { genes: '基因表达', tasks: '代谢任务', reactions: '反应评分' }[item] }}</button></div>
              <p class="table-unit">单位：{{ units || '未提供' }}。{{ tableKind === 'genes' ? '表达值为 mean(log1p(CP10K))。' : '代谢评分由实测表达推断，不代表实测通量、代谢物浓度或酶活性。' }}</p>
              <template v-if="tableKind === 'genes' || metabolismAvailable">
                <form class="table-search" @submit.prevent="searchTable"><label for="measured-table-search" class="sr-only">检索当前结果表</label><input id="measured-table-search" v-model="tableSearch" class="input" placeholder="检索基因、任务或反应" maxlength="500"/><button class="btn" type="submit">检索</button></form>
                <p v-if="tableLoading" role="status">正在读取结果表…</p><div v-else-if="tableError" class="notice notice-danger" role="alert">{{ tableError }} <button class="btn btn-sm" @click="tableRefresh++">重新读取结果表</button></div><p v-else-if="!table?.items.length" class="empty-section">没有符合条件的结果。</p>
                <div v-else class="table-wrap"><table class="result-table"><thead><tr><th scope="col">{{ tableKind === 'genes' ? '基因' : tableKind === 'tasks' ? '任务' : '反应' }}</th><th scope="col">实测对照均值</th><th scope="col">实测扰动均值</th><th scope="col">差值（扰动 − 对照）</th><th v-if="tableKind === 'tasks'" scope="col">基因覆盖比例</th></tr></thead><tbody><tr v-for="row in table.items" :key="rowId(row)"><td><strong>{{ rowId(row) }}</strong><small v-if="row.label && row.label !== rowId(row)">{{ row.label }}</small></td><td>{{ numeric(row.control) }}</td><td>{{ numeric(row.observed) }}</td><td :class="{ 'delta-positive': (row.observed_delta ?? 0) > 0, 'delta-negative': (row.observed_delta ?? 0) < 0 }">{{ numeric(row.observed_delta) }}</td><td v-if="tableKind === 'tasks'">{{ row.gene_fraction == null ? '—' : `${numeric(row.gene_fraction * 100)}%` }}</td></tr></tbody></table></div>
                <footer v-if="table" class="pagination"><span>共 {{ table.total }} 条 · 第 {{ tablePage }} / {{ tablePages }} 页</span><div class="btn-row"><button class="btn btn-sm" :disabled="tablePage <= 1 || tableLoading" @click="tablePage--">上一页</button><button class="btn btn-sm" :disabled="tablePage >= tablePages || tableLoading" @click="tablePage++">下一页</button></div></footer>
              </template><p v-else class="empty-section">代谢分析不可用：{{ summary.metabolism.reason || '未生成可核验的代谢评分产物' }}。实测表达比较仍然可用。</p>
            </details>
            <details class="card"><summary>数据来源、解释边界与报告</summary>
              <div class="section-heading"><h2>数据来源与解释边界</h2><button class="btn" :disabled="!!downloading" @click="download('report')">{{ downloading === 'report' ? '正在下载…' : '下载 HTML 报告' }}</button></div>
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
</style>
