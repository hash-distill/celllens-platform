<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
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

const props = defineProps<{ runId: string }>()
const runs = useRunStore(), entry = computed(() => runs.entry(props.runId))
const tasks = computed(() => (entry.value?.tasks.data?.items ?? []).filter(hasPredictionChange))
const synthetic = computed(() => isSyntheticResult(entry.value?.record?.request.mode, props.runId, entry.value?.record?.result_kind))
const search = ref(''), category = ref(''), sort = ref('change')
const categories = computed(() => [...new Set(tasks.value.map(task => task.category).filter((value): value is string => !!value))].sort())
const filtered = computed(() => tasks.value.filter(task => (!category.value || task.category === category.value) && `${task.label} ${task.id}`.toLowerCase().includes(search.value.trim().toLowerCase())).slice().sort((a,b) => sort.value === 'name' ? a.label.localeCompare(b.label) : Math.abs(b.predicted_delta)-Math.abs(a.predicted_delta)))
const { page, pageSize, pages, visible } = usePagedRows(filtered)
const taskId = ref(''), reactionId = ref(''), selected = ref('task:')
const projectionMethod = ref<'pca'|'umap'>('umap')
const task = computed(() => tasks.value.find(row => row.id === taskId.value))
const trace = ref<TaskTraceResponse | null>(null), traceError = ref(''), loading = ref(false)
let traceController: AbortController | undefined
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
watch(filtered, rows => { if (!rows.some(row => row.id === taskId.value)) taskId.value = rows[0]?.id ?? '' }, {immediate:true})
async function loadTrace() {
  traceController?.abort()
  const controller = traceController = new AbortController(), id = props.runId, chosen = taskId.value
  trace.value = null; traceError.value = ''; reactionId.value = ''; selected.value = 'task:'+chosen; loading.value = false
  if (!chosen) return
  if (synthetic.value || task.value?.trace_available === false) { traceError.value = '本次运行未提供可核验的功能关联记录。保留任务分数。'; return }
  loading.value = true
  try {
    const data = await api.getFunctionTrace(id, chosen, controller.signal)
    if (controller.signal.aborted || id !== props.runId || chosen !== taskId.value) return
    trace.value = predictionTrace(data); reactionId.value = trace.value?.reactions[0]?.id ?? ''
  } catch (error) {
    if (!controller.signal.aborted) traceError.value = '功能关联读取失败：'+(error instanceof Error ? error.message : '未知错误')
  } finally { if (!controller.signal.aborted) loading.value = false }
}
watch([() => props.runId, taskId, () => task.value?.trace_available, synthetic], loadTrace, {immediate:true})
function choose(kind: NodeKind, id: string) { selected.value = kind+':'+id }
function chooseReaction(id: string) { reactionId.value = id; selected.value = 'reaction:'+id }
function exportTrace() {
  if (!trace.value) return
  downloadBlob(new Blob([JSON.stringify({ ...trace.value, display:{selected_reaction:reactionId.value, embedding:projectionMethod.value, space:'metabolic', filter:'complete-finite-nonzero-prediction', observed_mean:'control + saved observed_delta'}, result_source:entry.value?.record },null,2)],{type:'application/json'}),`${props.runId}_function_${encodeURIComponent(taskId.value)}.json`)
}
onBeforeUnmount(() => traceController?.abort())
</script>
<template>
  <section class="function-workspace" aria-label="功能前后对比" :data-run="runId">
    <header class="function-heading"><div><span class="eyebrow">MODEL PREDICTION / FUNCTION</span><h2>模型预测哪些代谢功能发生变化？</h2><p>按任务查看预测变化，以及关联的反应与基因。</p></div><span class="pill pill-neutral">{{ runSourceLabel(entry?.record?.request.mode,runId,entry?.record?.result_kind) }}</span></header>
    <p v-if="synthetic" class="notice notice-warn">此历史记录为合成数据，功能关联分析不可用。</p>
    <div v-if="entry?.tasks.status==='error'" class="notice notice-warn">任务结果读取失败。<button class="btn btn-sm" @click="runs.retryBlock(runId,'tasks')">重试任务</button></div>
    <p v-else-if="entry?.tasks.status!=='ok'" class="notice">正在读取本次运行的功能任务…</p>
    <div v-else class="function-layout">
      <aside class="task-browser" aria-label="功能任务列表">
        <header><h3>代谢任务 <small>{{ filtered.length }} / {{ tasks.length }}</small></h3><p>按变化幅度排序，不代表统计显著性。</p></header>
        <label>搜索任务<input v-model="search" type="search" placeholder="名称或任务 ID" aria-label="搜索功能任务" /></label>
        <label>功能分类<select v-model="category" aria-label="功能分类"><option value="">全部分类</option><option v-for="item in categories" :key="item" :value="item">{{ item }}</option></select></label>
        <label>排序<select v-model="sort" aria-label="功能任务排序"><option value="change">变化幅度</option><option value="name">任务名称</option></select></label>
        <div class="task-options"><button v-for="item in visible" :key="item.id" class="task-option" :class="{active:taskId===item.id}" :aria-pressed="taskId===item.id" :data-task="item.id" @click="taskId=item.id"><span>{{ item.label }}</span><small>{{ item.category || '分类未提供' }}</small><strong :class="item.predicted_delta<0?'negative':'positive'">Δ {{ fmtDelta(item.predicted_delta,3) }}</strong></button><p v-if="!filtered.length" class="muted">未找到匹配的任务，请调整筛选条件。</p></div>
        <TablePager v-model:page="page" v-model:page-size="pageSize" :pages="pages" :total="filtered.length" />
        <small class="scope-note">{{ entry?.tasks.data?.scope==='all'?'本次已评分任务':'本次保存的 Top 摘要' }}{{ entry?.tasks.data?.truncated?'（已截断）':'' }}；未评分任务不补零。</small>
      </aside>
      <section class="function-main" aria-label="当前功能关联">
        <header class="task-heading"><span class="eyebrow">SELECTED FUNCTION</span><h3>{{ task?.label || '请选择任务' }}</h3><p v-if="task">{{ task.id }} · {{ task.category || '分类未提供' }}{{ task.subcategory?' / '+task.subcategory:'' }}</p></header>
        <div class="mode-controls" aria-label="代谢降维方式"><button class="btn btn-sm" :class="{'btn-primary':projectionMethod==='umap'}" :aria-pressed="projectionMethod==='umap'" @click="projectionMethod='umap'">UMAP</button><button class="btn btn-sm" :class="{'btn-primary':projectionMethod==='pca'}" :aria-pressed="projectionMethod==='pca'" @click="projectionMethod='pca'">PCA</button><span class="projection-label">逐细胞代谢任务空间 · 所选任务着色</span><button class="btn btn-sm export-trace" :disabled="!trace" @click="exportTrace">导出关联 JSON</button></div>
        <CellStateTab v-if="taskId && !synthetic" :run-id="runId" :embedding="projectionMethod" space="metabolic" feature-kind="task" :feature-id="taskId" />
        <details v-if="trace?.reactions.length || loading || traceError" class="association-evidence"><summary>有预测变化的反应与基因</summary>
        <p v-if="loading" class="network-message" role="status">正在读取完整功能关联…</p>
        <div v-else-if="traceError" class="network-message" role="status"><p>{{ traceError }}</p><button v-if="!synthetic && task?.trace_available!==false" class="btn btn-sm" @click="loadTrace">重试功能关联</button></div>
        <template v-else-if="trace">
          <section class="reaction-browser" aria-label="关联反应列表"><header><h3>有预测变化的反应</h3><span>{{ reactions.length }} 个反应 · {{ relatedGeneIds }} 个不同基因</span></header><p>点击反应查看评分和关联基因。</p><div class="reaction-options"><button v-for="row in reactionRows" :key="row.id" class="btn btn-sm" :class="{'btn-primary':reactionId===row.id}" :aria-pressed="reactionId===row.id" :title="row.label" :data-reaction="row.id" @click="chooseReaction(row.id)">{{ row.id }} <small>{{ fmtDelta(row.predicted_delta,3) }}</small></button></div><TablePager v-model:page="reactionPage" v-model:page-size="reactionPageSize" :pages="reactionPages" :total="reactions.length" /><p v-if="trace.truncated" class="notice notice-warn">关联记录已截断，当前不是完整关联列表。</p></section>
          <p class="trace-notes">数值来自本次模型预测。表达、反应和任务分数单位不同；关联不代表因果贡献或实测通量。</p>
        </template>
        </details>
        <p v-if="!task" class="network-message">当前筛选下没有符合展示标准的任务。</p>
      </section>
      <aside class="node-detail" aria-label="功能节点详情">
        <span class="eyebrow">NODE / EVIDENCE</span><h3>{{ KIND_LABEL[selectedKind] || '任务分数' }}</h3><h4>{{ score?.label || '请选择节点' }}</h4><p class="mono identifier">{{ score?.id }}</p>
        <dl v-if="score" class="node-scores"><div><dt>对照</dt><dd data-score="control">{{ fmtNumber(score.control) }}</dd></div><div><dt>模型预测</dt><dd data-score="predicted">{{ fmtNumber(score.predicted) }}</dd></div><div><dt>预测 − 对照</dt><dd data-score="delta">{{ fmtDelta(score.predicted_delta) }}</dd></div><div v-if="score.observed_delta != null"><dt>{{ synthetic?'合成观测差值':'实测 − 对照' }}</dt><dd data-score="observed">{{ fmtDelta(score.observed_delta) }}</dd></div></dl>
        <p v-if="score && score.control == null && score.predicted == null" class="detail-note">{{ selectedKind === 'gene' ? '该名称来自知识库关联，本次没有该基因的有效表达值。' : '该名称来自知识库关联，本次没有有效反应分数。' }}关联名称与可评分数值是不同信息。</p>
        <p class="detail-note">{{ selectedKind==='gene'?'表达单位：':selectedKind==='reaction'?'反应单位：':'任务单位：' }}{{ trace?.score_units?.[selectedKind] || '请查阅本次运行来源' }}</p>
        <p v-if="selectedKind!=='gene'" class="detail-note"><RouterLink :to="{path:'/coverage',query:{run:runId,task:taskId}}">查看当前任务的基因范围与缺失项 ↗</RouterLink></p>
        <section v-if="reaction" class="gpr-detail"><h4>有预测变化的关联基因</h4><button v-for="gene in reaction.genes" :key="gene.id" class="gene-link" @click="choose('gene',gene.id)">{{ gene.label }} · Δ {{ fmtDelta(gene.predicted_delta,3) }}</button></section>
        <section class="provenance-detail"><h4>本次来源</h4><p class="mono">{{ runId }}</p><RouterLink v-if="entry?.provenance.data?.source_run_id" :to="{path:'/demo',query:{run:entry.provenance.data.source_run_id,tab:'metabolism',view:'function'}}">原始真实运行：{{ entry.provenance.data.source_run_id }} ↗</RouterLink><p>{{ trace?.database_version || '知识库版本未提供' }}</p><details v-if="trace"><summary>冻结知识库哈希</summary><p class="mono">{{ trace.database_provenance.manifest_sha256 }}</p></details><RouterLink :to="{path:'/demo',query:{run:runId,tab:'metabolism',view:'data'}}">完整代谢评分 ↗</RouterLink><RouterLink :to="{path:'/demo',query:{run:runId,tab:'validation'}}">本次预测验证 ↗</RouterLink></section>
      </aside>
    </div>
    <footer class="function-boundary">代谢坐标来自本次逐细胞 scCellFie 任务分数，不代表细胞形态或空间位置。分数不等于代谢通量；细胞没有逐点配对，差值大小不代表统计显著性。</footer>
  </section>
</template>
<style scoped>
.function-workspace{min-width:0}.function-heading{display:flex;justify-content:space-between;gap:20px;align-items:center;margin:25px 0}.function-heading h2{font-size:24px;font-weight:500;margin:10px 0}.function-heading p{font-size:12px;color:var(--muted);line-height:1.8}.function-heading .pill{white-space:normal;max-width:210px}.function-layout{display:grid;grid-template-columns:230px minmax(0,1fr);gap:16px;align-items:start}.task-browser,.function-main,.node-detail{border:1px solid var(--border);background:var(--card);padding:18px;min-width:0}h3{font-size:15px;font-weight:500;margin:0 0 10px}h4{font-size:13px;font-weight:500;line-height:1.7;margin:12px 0}.task-browser header p,.reaction-browser p{font-size:10px;color:var(--muted);line-height:1.7}.task-browser h3 small{font-size:10px;color:var(--muted)}label{display:block;color:var(--muted);font-size:10px;margin:12px 0}input,select{display:block;width:100%;min-width:0;margin-top:6px;padding:9px;border:1px solid var(--border);background:var(--card);color:var(--ink);font:11px var(--font)}.task-options{max-height:490px;overflow:auto;margin-top:16px}.task-option{display:block;width:100%;text-align:left;border:0;border-bottom:1px solid var(--border);padding:13px 10px;background:transparent;cursor:pointer;color:var(--ink)}.task-option span{display:block;font-size:11px;line-height:1.6}.task-option small{display:block;color:var(--muted);font-size:9px;margin:6px 0}.task-option strong{font:11px Consolas,monospace}.task-option.active{background:var(--primary-weak);box-shadow:inset 3px 0 var(--primary)}.task-option:hover{background:var(--surface-tint-hover)}.negative{color:var(--delta-down)}.positive{color:var(--delta-up)}.scope-note{display:block;font-size:9px;color:var(--muted);margin-top:12px;line-height:1.8}.task-heading h3{font-size:18px;line-height:1.6;margin:10px 0}.task-heading p{font:10px Consolas,monospace;color:var(--muted);overflow-wrap:anywhere}.mode-controls{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}.projection-label{font-size:11px;color:var(--muted);align-self:center}.association-evidence{margin-top:24px;border-top:1px solid var(--border);padding-top:18px}.association-evidence>summary{cursor:pointer;color:var(--primary);font-size:12px}.export-trace{margin-left:auto}.network-message{min-height:250px;padding:60px 20px;text-align:center;background:var(--message-bg);color:var(--muted);font-size:12px;line-height:1.9}.reaction-browser{border-top:1px solid var(--border);margin-top:24px;padding-top:20px}.reaction-browser header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.reaction-browser header span{font-size:10px;color:var(--muted)}.reaction-options{display:flex;flex-wrap:wrap;gap:6px;max-height:210px;overflow:auto}.reaction-options .btn{font-size:10px}.reaction-options small{margin-left:6px}.node-detail{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr 1fr;gap:0 24px}.node-detail>.eyebrow,.node-detail>h3,.node-detail>h4,.node-detail>.identifier{grid-column:1/-1}.node-detail .identifier{font-size:10px;color:var(--muted)}.node-scores{margin:20px 0}.node-scores div{display:flex;justify-content:space-between;gap:8px;border-bottom:1px solid var(--border);padding:12px 0}.node-scores dt{font-size:10px;color:var(--muted)}.node-scores dd{font:15px Consolas,monospace;margin:0}.detail-note,.coverage-detail p,.coverage-detail small,.gpr-detail p,.provenance-detail p{font-size:10px;line-height:1.9;color:var(--muted)}.node-detail section{border-top:1px solid var(--border);margin-top:18px;padding-top:4px}.coverage-detail strong{font:30px Georgia,serif;color:var(--primary)}.node-detail details{font-size:10px;line-height:1.8;margin:12px 0}.node-detail summary{cursor:pointer;color:var(--primary)}.node-detail code{display:block;font:11px Consolas,monospace;background:var(--code-bg);padding:12px;white-space:pre-wrap;overflow-wrap:anywhere}.node-detail p,.node-detail h4{overflow-wrap:anywhere}.gene-link{display:block;text-align:left;font:10px Consolas,monospace;padding:8px;border:0;border-bottom:1px solid var(--border);background:transparent;color:var(--primary);width:100%;cursor:pointer}.provenance-detail a{display:block;font-size:10px;line-height:2.4}.trace-notes{font-size:10px;color:var(--muted);line-height:1.9;margin-top:18px}.trace-notes summary{cursor:pointer;color:var(--primary)}.function-boundary{font-size:11px;line-height:2;color:var(--muted);border-top:1px solid var(--border);padding:18px 0;margin-top:22px}.task-browser :deep(.pager){gap:6px}.task-browser :deep(.pager span){flex-basis:100%;font-size:9px}
</style>
