<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../../api/client'
import { useRunStore } from '../../stores/run'
import { fmtNumber, fmtDelta } from '../../utils/format'
import { isSyntheticResult, runSourceLabel } from '../../utils/source'
import { downloadBlob } from '../../utils/csv'
import { usePagedRows } from '../../utils/pagination'
import { KIND_LABEL, layoutNodes } from '../../utils/functionNetwork'
import type { NodeKind } from '../../utils/functionNetwork'
import type { TaskTraceResponse, TraceScore } from '../../types/trace'
import CellStateTab from '../tabs/CellStateTab.vue'
import TablePager from '../TablePager.vue'
import { hasPredictionChange, predictionTrace } from '../../utils/predictionEvidence'
import { metabolicGroupName, taskName } from '../../utils/biologyLocale'
import { buildTraceExport } from '../../utils/exportArtifacts'
import { featureFilenameToken } from '../../utils/download'
import { coverageState } from '../../utils/resultOverview'

const props = defineProps<{ runId: string }>()
const route = useRoute()
const showCompleteAssociations = ref(false), projectionOpen = ref(false)
const runs = useRunStore(), entry = computed(() => runs.entry(props.runId))
const tasks = computed(() => (entry.value?.tasks.data?.items ?? []).filter(row => hasPredictionChange(row) || row.id === route.query.task))
const synthetic = computed(() => isSyntheticResult(entry.value?.record?.request.mode, props.runId, entry.value?.record?.result_kind))
const search = ref(''), category = ref(''), sort = ref('coverage')
const categories = computed(() => [...new Set(tasks.value.map(task => task.category).filter((value): value is string => !!value))].sort())
const filtered = computed(() => tasks.value.filter(task => (!category.value || task.category === category.value) && `${taskName(task.id, task.label)} ${task.label} ${task.id}`.toLowerCase().includes(search.value.trim().toLowerCase())).slice().sort((a,b) => {
  const names = (a.category ?? '').localeCompare(b.category ?? '') || taskName(a.id, a.label).localeCompare(taskName(b.id, b.label), 'zh-CN')
  if (sort.value === 'name') return taskName(a.id, a.label).localeCompare(taskName(b.id, b.label), 'zh-CN')
  const aCoverage = coverageState(a.coverage) === 'unknown' ? -1 : a.coverage
  const bCoverage = coverageState(b.coverage) === 'unknown' ? -1 : b.coverage
  return bCoverage - aCoverage || names
}))
const { page, pageSize, pages, visible } = usePagedRows(filtered)
const taskId = ref(''), reactionId = ref(''), selected = ref('task:')
const projectionMethod = ref<'pca'|'umap'>('umap')
const task = computed(() => tasks.value.find(row => row.id === taskId.value))
const rawTrace = ref<TaskTraceResponse | null>(null), traceError = ref(''), loading = ref(false)
const trace = computed(() => rawTrace.value ? showCompleteAssociations.value ? rawTrace.value : predictionTrace(rawTrace.value) : null)
const networkDownloading = ref(false), exportError = ref('')
let traceController: AbortController | undefined, networkController: AbortController | undefined
const reactions = computed(() => trace.value?.reactions ?? [])
const { page: reactionPage, pageSize: reactionPageSize, pages: reactionPages, visible: reactionRows } = usePagedRows(reactions)
const reaction = computed(() => reactions.value.find(row => row.id === reactionId.value))
const nodes = computed(() => trace.value ? layoutNodes(trace.value.task, reaction.value) : [])
const selectedKind = computed(() => selected.value.split(':')[0] as NodeKind)
const selectedNode = computed(() => nodes.value.find(node => node.kind+':'+node.score.id === selected.value))
const score = computed<TraceScore | undefined>(() => selectedNode.value?.score ?? (task.value ? { ...task.value, control:task.value.control ?? null, predicted:task.value.predicted ?? null } : undefined))
const relatedGeneIds = computed(() => new Set(reactions.value.flatMap(row => row.genes.map(gene => gene.id))).size)
watch([() => props.runId, () => entry.value?.record?.status], () => {
  if (entry.value?.record?.status === 'completed' && entry.value?.tasks.status === 'idle') void runs.loadTasks(props.runId)
}, {immediate:true})
watch(filtered, rows => { if (!rows.some(row => row.id === taskId.value)) taskId.value = rows.find(row => row.id === route.query.task)?.id ?? rows[0]?.id ?? '' }, {immediate:true})
watch(() => route.query.task, id => { if (typeof id === 'string') { search.value = ''; category.value = ''; taskId.value = id } }, {immediate:true})
watch(reactions, rows => { if (!rows.some(row => row.id === reactionId.value)) reactionId.value = rows[0]?.id ?? '' })
async function loadTrace() {
  traceController?.abort()
  networkController?.abort(); networkDownloading.value = false; exportError.value = ''
  const controller = traceController = new AbortController(), id = props.runId, chosen = taskId.value
  rawTrace.value = null; traceError.value = ''; reactionId.value = ''; selected.value = 'task:'+chosen; loading.value = false
  if (!chosen) return
  if (synthetic.value || task.value?.trace_available === false) { traceError.value = '本次实验暂无功能关联记录，可继续查看任务分数。'; return }
  loading.value = true
  try {
    const data = await api.getFunctionTrace(id, chosen, controller.signal)
    if (controller.signal.aborted || id !== props.runId || chosen !== taskId.value) return
    rawTrace.value = data; reactionId.value = trace.value?.reactions[0]?.id ?? ''
  } catch (error) {
    if (!controller.signal.aborted) traceError.value = '功能关联读取失败：'+(error instanceof Error ? error.message : '未知错误')
  } finally { if (!controller.signal.aborted) loading.value = false }
}
watch([() => props.runId, taskId, () => task.value?.trace_available, synthetic], loadTrace, {immediate:true})
function choose(kind: NodeKind, id: string) { selected.value = kind+':'+id }
function chooseReaction(id: string) { reactionId.value = id; selected.value = 'reaction:'+id }
async function exportTrace() {
  const snapshot = rawTrace.value, current = traceController
  if (!snapshot) return
  exportError.value = ''
  try {
    const output = {...buildTraceExport(snapshot, trace.value, {selected_reaction:reactionId.value,embedding:projectionMethod.value,space:'metabolic'}),result_source:entry.value?.record}
    const token = await featureFilenameToken(snapshot.task.id)
    if (current?.signal.aborted || snapshot !== rawTrace.value) return
    downloadBlob(new Blob([JSON.stringify(output,null,2)],{type:'application/json'}),`${snapshot.run_id}_function_${token}.json`)
  } catch(error) {if (!current?.signal.aborted && snapshot === rawTrace.value) exportError.value = error instanceof Error ? error.message : '完整关联导出失败'}
}
async function exportNetwork() {
  const snapshot = rawTrace.value
  if (!snapshot || synthetic.value || networkDownloading.value) return
  const current = networkController = new AbortController()
  networkDownloading.value = true; exportError.value = ''
  try {
    const result = await api.getExportPackage(snapshot.run_id,'network',current.signal,snapshot.task.id)
    if (!current.signal.aborted && snapshot === rawTrace.value) downloadBlob(result.blob,result.filename)
  } catch(error) {if (!current.signal.aborted) exportError.value = error instanceof Error ? error.message : '网络包下载失败'}
  finally {if (!current.signal.aborted) networkDownloading.value = false}
}
onBeforeUnmount(() => {traceController?.abort();networkController?.abort()})
</script>
<template>
  <section class="function-workspace" aria-label="功能前后对比" :data-run="runId">
    <header class="function-heading"><div><span class="eyebrow">MODEL PREDICTION / FUNCTION</span><h2>扰动前后细胞代谢状态的分布变化</h2><p>根据逐细胞代谢任务分数比较群体分布与预测变化，核对关联反应和基因；坐标表示功能特征，不表示细胞形态或真实位置。</p></div><span class="pill pill-neutral">{{ runSourceLabel(entry?.record?.request.mode,runId,entry?.record?.result_kind) }}</span></header>
    <p v-if="synthetic" class="notice notice-warn">此历史记录为合成数据，功能关联分析不可用。</p>
    <div v-if="entry?.tasks.status==='error'" class="notice notice-warn">任务结果读取失败。<button class="btn btn-sm" @click="runs.retryBlock(runId,'tasks')">重试任务</button></div>
    <p v-else-if="entry?.tasks.status!=='ok'" class="notice">正在读取本次运行的功能任务…</p>
    <div v-else class="function-layout">
      <aside class="task-browser" aria-label="功能任务列表">
        <header><h3>代谢任务 <small>{{ filtered.length }} / {{ tasks.length }}</small></h3><p>按覆盖与名称查找任务；变化仅在同一任务的群体间比较。</p></header>
        <label>搜索任务<input v-model="search" type="search" placeholder="名称或任务 ID" aria-label="搜索功能任务" /></label>
        <label>功能分类<select v-model="category" aria-label="功能分类"><option value="">全部分类</option><option v-for="item in categories" :key="item" :value="item">{{ metabolicGroupName(item) }}</option></select></label>
        <label>排序<select v-model="sort" aria-label="功能任务排序"><option value="coverage">覆盖与分类</option><option value="name">任务名称</option></select></label>
        <div class="task-options"><button v-for="item in visible" :key="item.id" class="task-option" :class="{active:taskId===item.id}" :aria-pressed="taskId===item.id" :data-task="item.id" @click="taskId=item.id"><span>{{ taskName(item.id, item.label) }}</span><small>{{ metabolicGroupName(item.category) }}</small><strong :class="item.predicted_delta<0?'negative':'positive'">Δ {{ fmtDelta(item.predicted_delta,3) }}</strong></button><p v-if="!filtered.length" class="muted">未找到匹配的任务，请调整筛选条件。</p></div>
        <TablePager v-model:page="page" v-model:page-size="pageSize" :pages="pages" :total="filtered.length" />
        <small class="scope-note">{{ entry?.tasks.data?.scope==='all'?'本次已评分任务':'主要响应任务' }}{{ entry?.tasks.data?.truncated?'（已截断）':'' }}。</small>
      </aside>
      <section class="function-main" aria-label="当前功能关联">
        <header class="task-heading"><span class="eyebrow">SELECTED FUNCTION</span><h3>{{ task ? taskName(task.id, task.label) : '请选择任务' }}</h3><p v-if="task">{{ task.id }} · {{ metabolicGroupName(task.category) }}{{ task.subcategory?' / '+metabolicGroupName(task.subcategory):'' }}</p></header>
        <div class="mode-controls" aria-label="代谢降维方式"><button class="btn btn-sm" :class="{'btn-primary':projectionMethod==='umap'}" :aria-pressed="projectionMethod==='umap'" @click="projectionMethod='umap'">UMAP</button><button class="btn btn-sm" :class="{'btn-primary':projectionMethod==='pca'}" :aria-pressed="projectionMethod==='pca'" @click="projectionMethod='pca'">PCA</button><span class="projection-label">代谢状态分布 · 所选任务分数着色</span><button class="btn btn-sm export-trace" :disabled="!rawTrace" @click="exportTrace">导出完整关联 JSON</button><button class="btn btn-sm" :disabled="!rawTrace || synthetic || networkDownloading" @click="exportNetwork">{{ networkDownloading?'下载中…':'所选任务网络包 ZIP' }}</button></div>
        <p v-if="exportError" class="notice notice-warn" role="alert">{{ exportError }}</p>
        <details @toggle="projectionOpen=($event.target as HTMLDetailsElement).open"><summary>专业检查：代谢任务投影</summary><CellStateTab v-if="projectionOpen && taskId && !synthetic" :run-id="runId" :embedding="projectionMethod" space="metabolic" feature-kind="task" :feature-id="taskId" /></details>
        <details v-if="rawTrace || loading || traceError" class="association-evidence" open><summary>反应与基因关联证据</summary><label><input v-model="showCompleteAssociations" type="checkbox" style="display:inline;width:auto;min-height:0" /> 完整知识库关联（含未变化及缺失成员）</label><p class="trace-notes">默认聚焦预测变化；完整模式保留 GPR 规则与缺失项。知识库关联不是本次实验验证的机制。</p>
        <p v-if="loading" class="network-message" role="status">正在读取完整功能关联…</p>
        <div v-else-if="traceError" class="network-message" role="status"><p>{{ traceError }}</p><button v-if="!synthetic && task?.trace_available!==false" class="btn btn-sm" @click="loadTrace">重试功能关联</button></div>
        <template v-else-if="trace">
          <section class="reaction-browser" aria-label="关联反应列表"><header><h3>{{ showCompleteAssociations ? '知识库关联反应' : '有预测变化的反应' }}</h3><span>{{ reactions.length }} 个反应 · {{ relatedGeneIds }} 个不同基因</span></header><p>点击反应查看评分和关联基因。</p><div class="reaction-options"><button v-for="row in reactionRows" :key="row.id" class="btn btn-sm" :class="{'btn-primary':reactionId===row.id}" :aria-pressed="reactionId===row.id" :title="row.label" :data-reaction="row.id" @click="chooseReaction(row.id)">{{ row.id }} <small>{{ fmtDelta(row.predicted_delta,3) }}</small></button></div><TablePager v-model:page="reactionPage" v-model:page-size="reactionPageSize" :pages="reactionPages" :total="reactions.length" /><p v-if="trace.truncated" class="notice notice-warn">关联记录已截断，当前不是完整关联列表。</p></section>
          <p class="trace-notes">选择反应或基因，查看对应的预测变化。</p>
        </template>
        </details>
        <p v-if="!task" class="network-message">当前筛选下没有符合展示标准的任务。</p>
      </section>
      <aside class="node-detail" aria-label="功能节点详情">
        <span class="eyebrow">NODE / EVIDENCE</span><h3>{{ KIND_LABEL[selectedKind] || '任务分数' }}</h3><h4>{{ score ? (selectedKind === 'task' ? taskName(score.id, score.label) : score.label) : '请选择节点' }}</h4><p class="mono identifier">{{ score?.id }}</p>
        <dl v-if="score" class="node-scores"><div><dt>对照</dt><dd data-score="control">{{ fmtNumber(score.control) }}</dd></div><div><dt>模型预测</dt><dd data-score="predicted">{{ fmtNumber(score.predicted) }}</dd></div><div><dt>预测 − 对照</dt><dd data-score="delta">{{ fmtDelta(score.predicted_delta) }}</dd></div><div v-if="score.observed_delta != null"><dt>{{ synthetic?'合成观测差值':'实测 − 对照' }}</dt><dd data-score="observed">{{ fmtDelta(score.observed_delta) }}</dd></div></dl>
        <p v-if="score && score.control == null && score.predicted == null" class="detail-note">{{ selectedKind === 'gene' ? '该名称来自知识库关联，本次没有该基因的有效表达值。' : '该名称来自知识库关联，本次没有有效反应分数。' }}</p>
        <p class="detail-note">{{ selectedKind==='gene'?'表达单位：':selectedKind==='reaction'?'反应单位：':'任务单位：' }}{{ trace?.score_units?.[selectedKind] || '请查阅本次运行来源' }}</p>
        <p v-if="selectedKind!=='gene'" class="detail-note"><RouterLink :to="{path:'/coverage',query:{run:runId,task:taskId}}">查看当前任务的基因范围与缺失项 ↗</RouterLink></p>
        <section v-if="reaction" class="gpr-detail"><h4>{{ showCompleteAssociations ? '全部关联基因' : '有预测变化的关联基因' }}</h4><code v-if="showCompleteAssociations && reaction.gene_rule">{{ reaction.gene_rule }}</code><button v-for="gene in reaction.genes" :key="gene.id" class="gene-link" @click="choose('gene',gene.id)">{{ gene.label }} · Δ {{ fmtDelta(gene.predicted_delta,3) }}</button></section>
        <section class="provenance-detail"><h4>本次来源</h4><p class="mono">{{ runId }}</p><RouterLink v-if="entry?.provenance.data?.source_run_id" :to="{path:'/demo',query:{run:entry.provenance.data.source_run_id,tab:'metabolism',view:'function'}}">原始实验：{{ entry.provenance.data.source_run_id }} ↗</RouterLink><p>{{ trace?.database_version || '知识库版本未提供' }}</p><RouterLink :to="{path:'/demo',query:{run:runId,tab:'metabolism',view:'data'}}">完整代谢评分 ↗</RouterLink><RouterLink :to="{path:'/demo',query:{run:runId,tab:'comparison'}}">查看实测对比 ↗</RouterLink></section>
      </aside>
    </div>
  </section>
</template>
<style scoped>
.function-workspace{min-width:0}.function-heading{display:flex;justify-content:space-between;gap:20px;align-items:center;margin:25px 0}.function-heading h2{font-size:24px;font-weight:500;margin:10px 0}.function-heading p{font-size:12px;color:var(--muted);line-height:1.8}.function-heading .pill{white-space:normal;max-width:210px}.function-layout{display:grid;grid-template-columns:230px minmax(0,1fr);gap:16px;align-items:start}.task-browser,.function-main,.node-detail{border:1px solid var(--border);background:var(--card);padding:18px;min-width:0}h3{font-size:15px;font-weight:500;margin:0 0 10px}h4{font-size:13px;font-weight:500;line-height:1.7;margin:12px 0}.task-browser header p,.reaction-browser p{font-size:10px;color:var(--muted);line-height:1.7}.task-browser h3 small{font-size:10px;color:var(--muted)}label{display:block;color:var(--muted);font-size:10px;margin:12px 0}input,select{display:block;width:100%;min-width:0;margin-top:6px;padding:9px;border:1px solid var(--border);background:var(--card);color:var(--ink);font:11px var(--font)}.task-options{max-height:490px;overflow:auto;margin-top:16px}.task-option{display:block;width:100%;text-align:left;border:0;border-bottom:1px solid var(--border);padding:13px 10px;background:transparent;cursor:pointer;color:var(--ink)}.task-option span{display:block;font-size:11px;line-height:1.6}.task-option small{display:block;color:var(--muted);font-size:9px;margin:6px 0}.task-option strong{font:11px Consolas,monospace}.task-option.active{background:var(--primary-weak);box-shadow:inset 3px 0 var(--primary)}.task-option:hover{background:var(--surface-tint-hover)}.negative{color:var(--delta-down)}.positive{color:var(--delta-up)}.scope-note{display:block;font-size:9px;color:var(--muted);margin-top:12px;line-height:1.8}.task-heading h3{font-size:18px;line-height:1.6;margin:10px 0}.task-heading p{font:10px Consolas,monospace;color:var(--muted);overflow-wrap:anywhere}.mode-controls{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}.projection-label{font-size:11px;color:var(--muted);align-self:center}.association-evidence{margin-top:24px;border-top:1px solid var(--border);padding-top:18px}.association-evidence>summary{cursor:pointer;color:var(--primary);font-size:12px}.export-trace{margin-left:auto}.network-message{min-height:250px;padding:60px 20px;text-align:center;background:var(--message-bg);color:var(--muted);font-size:12px;line-height:1.9}.reaction-browser{border-top:1px solid var(--border);margin-top:24px;padding-top:20px}.reaction-browser header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.reaction-browser header span{font-size:10px;color:var(--muted)}.reaction-options{display:flex;flex-wrap:wrap;gap:6px;max-height:210px;overflow:auto}.reaction-options .btn{font-size:10px}.reaction-options small{margin-left:6px}.node-detail{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr 1fr;gap:0 24px}.node-detail>.eyebrow,.node-detail>h3,.node-detail>h4,.node-detail>.identifier{grid-column:1/-1}.node-detail .identifier{font-size:10px;color:var(--muted)}.node-scores{margin:20px 0}.node-scores div{display:flex;justify-content:space-between;gap:8px;border-bottom:1px solid var(--border);padding:12px 0}.node-scores dt{font-size:10px;color:var(--muted)}.node-scores dd{font:15px Consolas,monospace;margin:0}.detail-note,.coverage-detail p,.coverage-detail small,.gpr-detail p,.provenance-detail p{font-size:10px;line-height:1.9;color:var(--muted)}.node-detail section{border-top:1px solid var(--border);margin-top:18px;padding-top:4px}.coverage-detail strong{font:30px Georgia,serif;color:var(--primary)}.node-detail details{font-size:10px;line-height:1.8;margin:12px 0}.node-detail summary{cursor:pointer;color:var(--primary)}.node-detail code{display:block;font:11px Consolas,monospace;background:var(--code-bg);padding:12px;white-space:pre-wrap;overflow-wrap:anywhere}.node-detail p,.node-detail h4{overflow-wrap:anywhere}.gene-link{display:block;text-align:left;font:10px Consolas,monospace;padding:8px;border:0;border-bottom:1px solid var(--border);background:transparent;color:var(--primary);width:100%;cursor:pointer}.provenance-detail a{display:block;font-size:10px;line-height:2.4}.trace-notes{font-size:10px;color:var(--muted);line-height:1.9;margin-top:18px}.trace-notes summary{cursor:pointer;color:var(--primary)}.function-boundary{font-size:11px;line-height:2;color:var(--muted);border-top:1px solid var(--border);padding:18px 0;margin-top:22px}.task-browser :deep(.pager){gap:6px}.task-browser :deep(.pager span){flex-basis:100%;font-size:9px}
</style>
