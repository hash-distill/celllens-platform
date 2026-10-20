<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '../../api/client'
import { useRunStore } from '../../stores/run'
import { fmtNumber, fmtDelta, fmtPercent } from '../../utils/format'
import { isSyntheticResult, runSourceLabel } from '../../utils/source'
import { downloadBlob } from '../../utils/csv'
import { usePagedRows } from '../../utils/pagination'
import { KIND_LABEL, layoutNodes, nodeValue } from '../../utils/functionNetwork'
import type { NodeKind } from '../../utils/functionNetwork'
import type { TaskTraceResponse, TraceScore } from '../../types/trace'
import type { CompletenessResponse } from '../../types/completeness'
import FunctionNetwork from './FunctionNetwork.vue'
import TablePager from '../TablePager.vue'

const props = defineProps<{ runId: string }>()
const runs = useRunStore(), entry = computed(() => runs.entry(props.runId))
const tasks = computed(() => entry.value?.tasks.data?.items ?? [])
const synthetic = computed(() => isSyntheticResult(entry.value?.record?.request.mode, props.runId, entry.value?.record?.result_kind))
const search = ref(''), category = ref(''), sort = ref('change')
const categories = computed(() => [...new Set(tasks.value.map(task => task.category).filter((value): value is string => !!value))].sort())
const filtered = computed(() => tasks.value.filter(task => (!category.value || task.category === category.value) && `${task.label} ${task.id}`.toLowerCase().includes(search.value.trim().toLowerCase())).slice().sort((a,b) => sort.value === 'name' ? a.label.localeCompare(b.label) : Math.abs(b.predicted_delta)-Math.abs(a.predicted_delta)))
const { page, pages, visible } = usePagedRows(filtered)
const taskId = ref(''), reactionId = ref(''), selected = ref('task:'), mode = ref<'compare'|'delta'|'observed'>('compare')
const task = computed(() => tasks.value.find(row => row.id === taskId.value))
const trace = ref<TaskTraceResponse | null>(null), traceError = ref(''), loading = ref(false)
const official = ref<CompletenessResponse | null>(null), coverageError = ref('')
let traceController: AbortController | undefined, coverageController: AbortController | undefined
const reactions = computed(() => trace.value?.reactions ?? [])
const { page: reactionPage, pages: reactionPages, visible: reactionRows } = usePagedRows(reactions)
const reaction = computed(() => reactions.value.find(row => row.id === reactionId.value))
const nodes = computed(() => trace.value ? layoutNodes(trace.value.task, reaction.value) : [])
const hasObserved = computed(() => !synthetic.value && nodes.value.some(node => nodeValue(node.score,'observed') !== null))
const selectedKind = computed(() => selected.value.split(':')[0] as NodeKind)
const selectedNode = computed(() => nodes.value.find(node => node.kind+':'+node.score.id === selected.value))
const score = computed<TraceScore | undefined>(() => selectedNode.value?.score ?? (task.value ? { ...task.value, control:task.value.control ?? null, predicted:task.value.predicted ?? null } : undefined))
const coverage = computed(() => {
  if (!score.value || selectedKind.value === 'gene') return undefined
  return (selectedKind.value === 'reaction' ? official.value?.reactions : official.value?.tasks)?.find(row => row.id === score.value!.id)
})
const relatedGeneIds = computed(() => new Set(reactions.value.flatMap(row => row.genes.map(gene => gene.id))).size)
const warningLabels: Record<string,string> = {
  'Edges are frozen database knowledge associations, not causal contributions or measured flux.':'连线来自冻结知识库，表示关联，不代表因果贡献或实测通量。',
  'Determinant genes are unavailable: the engine output has not been validated for source-specific attribution.':'本次未提供经验证的驱动基因归因，关联基因不视为已证明的驱动基因。',
  'Missing or non-finite run scores are null; gene and metabolic score units differ.':'缺失和非有限分数保留为空；基因表达与代谢分数使用不同单位。',
}
watch([() => props.runId, () => entry.value?.record?.status], () => {
  if (entry.value?.record?.status === 'completed' && entry.value?.tasks.status === 'idle') void runs.loadTasks(props.runId)
}, {immediate:true})
watch(filtered, rows => { if (!rows.some(row => row.id === taskId.value)) taskId.value = rows[0]?.id ?? '' }, {immediate:true})
async function loadTrace() {
  traceController?.abort()
  const controller = traceController = new AbortController(), id = props.runId, chosen = taskId.value
  trace.value = null; traceError.value = ''; reactionId.value = ''; selected.value = 'task:'+chosen; mode.value = 'compare'; loading.value = false
  if (!chosen) return
  if (synthetic.value || task.value?.trace_available === false) { traceError.value = '本次运行未提供可核验的功能关联记录。保留任务分数；功能网络不可用。'; return }
  loading.value = true
  try {
    const data = await api.getFunctionTrace(id, chosen, controller.signal)
    if (controller.signal.aborted || id !== props.runId || chosen !== taskId.value) return
    trace.value = data; reactionId.value = data.reactions[0]?.id ?? ''
  } catch (error) {
    if (!controller.signal.aborted) traceError.value = '功能关联读取失败：'+(error instanceof Error ? error.message : '未知错误')
  } finally { if (!controller.signal.aborted) loading.value = false }
}
watch([() => props.runId, taskId, () => task.value?.trace_available, synthetic], loadTrace, {immediate:true})
async function loadCoverage() {
  coverageController?.abort(); official.value = null; coverageError.value = ''
  if (!entry.value?.tasks.data?.completeness_available || synthetic.value) return
  const controller = coverageController = new AbortController(), id = props.runId
  try { const data = await api.getCompleteness(id,controller.signal); if (!controller.signal.aborted && id === props.runId) official.value = data }
  catch(error) { if (!controller.signal.aborted) coverageError.value = error instanceof Error ? error.message : '读取失败' }
}
watch([() => props.runId, () => entry.value?.tasks.data?.completeness_available, synthetic], loadCoverage, {immediate:true})
watch(hasObserved, available => { if (!available && mode.value === 'observed') mode.value = 'compare' })
function choose(kind: NodeKind, id: string) { selected.value = kind+':'+id }
function chooseReaction(id: string) { reactionId.value = id; selected.value = 'reaction:'+id }
function exportTrace() {
  if (!trace.value) return
  downloadBlob(new Blob([JSON.stringify({ ...trace.value, display:{selected_reaction:reactionId.value, mode:mode.value, layout:'gene-reaction-task association', observed_mean:'control + saved observed_delta'}, result_source:entry.value?.record },null,2)],{type:'application/json'}),`${props.runId}_function_${encodeURIComponent(taskId.value)}.json`)
}
onBeforeUnmount(() => { traceController?.abort(); coverageController?.abort() })
</script>
<template>
  <section class="function-workspace" aria-label="功能前后对比" :data-run="runId">
    <header class="function-heading"><div><span class="eyebrow">PERTURBATION / FUNCTION</span><h2>扰动前后，细胞功能如何改变？</h2><p>选择代谢任务，比较表达与功能分数，再查看关联规则和覆盖证据。</p></div><span class="pill pill-neutral">{{ runSourceLabel(entry?.record?.request.mode,runId,entry?.record?.result_kind) }}</span></header>
    <p v-if="synthetic" class="notice notice-warn">此历史记录为示例数据，功能关联网络暂不提供。</p>
    <div v-if="entry?.tasks.status==='error'" class="notice notice-warn">任务结果读取失败。<button class="btn btn-sm" @click="runs.retryBlock(runId,'tasks')">重试任务</button></div>
    <p v-else-if="entry?.tasks.status!=='ok'" class="notice">正在读取本次运行的功能任务…</p>
    <div v-else class="function-layout">
      <aside class="task-browser" aria-label="功能任务列表">
        <header><h3>代谢任务 <small>{{ filtered.length }} / {{ tasks.length }}</small></h3><p>按变化幅度排序，不代表统计显著性。</p></header>
        <label>搜索任务<input v-model="search" type="search" placeholder="名称或任务 ID" aria-label="搜索功能任务" /></label>
        <label>功能分类<select v-model="category" aria-label="功能分类"><option value="">全部分类</option><option v-for="item in categories" :key="item" :value="item">{{ item }}</option></select></label>
        <label>排序<select v-model="sort" aria-label="功能任务排序"><option value="change">变化幅度</option><option value="name">任务名称</option></select></label>
        <div class="task-options"><button v-for="item in visible" :key="item.id" class="task-option" :class="{active:taskId===item.id}" :aria-pressed="taskId===item.id" :data-task="item.id" @click="taskId=item.id"><span>{{ item.label }}</span><small>{{ item.category || '分类未提供' }}</small><strong :class="item.predicted_delta<0?'negative':'positive'">Δ {{ fmtDelta(item.predicted_delta,3) }}</strong></button><p v-if="!filtered.length" class="muted">未找到匹配的任务，请调整筛选条件。</p></div>
        <TablePager v-model:page="page" :pages="pages" :total="filtered.length" />
        <small class="scope-note">{{ entry?.tasks.data?.scope==='all'?'本次已评分任务':'本次保存的 Top 摘要' }}{{ entry?.tasks.data?.truncated?'（已截断）':'' }}；未评分任务不补零。</small>
      </aside>
      <section class="function-main" aria-label="当前功能关联">
        <header class="task-heading"><span class="eyebrow">SELECTED FUNCTION</span><h3>{{ task?.label || '请选择任务' }}</h3><p v-if="task">{{ task.id }} · {{ task.category || '分类未提供' }}{{ task.subcategory?' / '+task.subcategory:'' }}</p></header>
        <div class="mode-controls" aria-label="功能对比方式"><button class="btn btn-sm" :class="{'btn-primary':mode==='compare'}" :aria-pressed="mode==='compare'" @click="mode='compare'">前后对比</button><button class="btn btn-sm" :class="{'btn-primary':mode==='delta'}" :aria-pressed="mode==='delta'" @click="mode='delta'">变化量</button><button v-if="hasObserved" class="btn btn-sm" :class="{'btn-primary':mode==='observed'}" :aria-pressed="mode==='observed'" @click="mode='observed'">预测与实测</button><RouterLink v-if="taskId && !synthetic" class="btn btn-sm" :to="{path:'/workbench',query:{run:runId,tab:'cell',feature_kind:'task',feature_id:taskId}}">查看逐细胞功能分布</RouterLink><button class="btn btn-sm export-trace" :disabled="!trace" @click="exportTrace">导出关联 JSON</button></div>
        <p v-if="loading" class="network-message" role="status">正在读取完整功能关联…</p>
        <div v-else-if="traceError" class="network-message" role="status"><p>{{ traceError }}</p><button v-if="!synthetic && task?.trace_available!==false" class="btn btn-sm" @click="loadTrace">重试功能关联</button></div>
        <template v-else-if="trace">
          <p class="network-caption">同一任务 · 同一反应 · {{ reaction?.genes.length ?? 0 }} 个关联基因 · 两侧共用节点位置和各类色标</p>
          <div class="network-comparison" :class="{single:mode==='delta'}">
            <FunctionNetwork v-if="mode==='compare'" :nodes="nodes" source="control" label="扰动前 / 对照" :selected="selected" @select="choose" />
            <FunctionNetwork :nodes="nodes" :source="mode==='delta'?'delta':'predicted'" :label="mode==='delta'?'功能变化量':'扰动后 / 模型预测'" :selected="selected" @select="choose" />
            <FunctionNetwork v-if="mode==='observed'" :nodes="nodes" source="observed" label="扰动后 / 实测群体" :selected="selected" @select="choose" />
          </div>
          <p class="color-note"><i class="cool"></i>{{ mode==='delta'?'下降':'负值' }} <i class="warm"></i>{{ mode==='delta'?'上升':'正值（越深越高）' }} <i class="zero"></i>零 <i class="missing"></i>缺失（虚线） · {{ mode!=='delta'?'升降请查看“变化量”。':'' }}同类节点独立缩放；表达、反应、任务分数不能跨类比较。连线表示知识库关联。</p>
          <section class="reaction-browser" aria-label="关联反应列表"><header><h3>关联反应</h3><span>{{ reactions.length }} / {{ trace.total_reactions }} 个反应 · {{ relatedGeneIds }} 个不同基因</span></header><p>点击反应展开其全部关联基因。当前图是该任务的局部网络。</p><div class="reaction-options"><button v-for="row in reactionRows" :key="row.id" class="btn btn-sm" :class="{'btn-primary':reactionId===row.id}" :aria-pressed="reactionId===row.id" :title="row.label" :data-reaction="row.id" @click="chooseReaction(row.id)">{{ row.id }} <small>{{ fmtDelta(row.predicted_delta,3) }}</small></button></div><TablePager v-model:page="reactionPage" :pages="reactionPages" :total="reactions.length" /><p v-if="trace.truncated" class="notice notice-warn">关联记录已截断，当前不是完整网络。</p><p v-if="!reactions.length">该任务没有保存反应关联，仅展示任务节点。</p></section>
          <details class="trace-notes"><summary>本次关联说明（{{ trace.warnings.length }}）</summary><p v-for="warning in trace.warnings" :key="warning">{{ warningLabels[warning] || warning }}</p></details>
        </template>
        <p v-else-if="!task" class="network-message">当前筛选下没有可展示任务。</p>
      </section>
      <aside class="node-detail" aria-label="功能节点详情">
        <span class="eyebrow">NODE / EVIDENCE</span><h3>{{ KIND_LABEL[selectedKind] || '任务分数' }}</h3><h4>{{ score?.label || '请选择节点' }}</h4><p class="mono identifier">{{ score?.id }}</p>
        <dl v-if="score" class="node-scores"><div><dt>对照</dt><dd data-score="control">{{ fmtNumber(score.control) }}</dd></div><div><dt>模型预测</dt><dd data-score="predicted">{{ fmtNumber(score.predicted) }}</dd></div><div><dt>预测 − 对照</dt><dd data-score="delta">{{ fmtDelta(score.predicted_delta) }}</dd></div><div><dt>{{ synthetic?'合成观测差值':'实测 − 对照' }}</dt><dd data-score="observed">{{ fmtDelta(score.observed_delta) }}</dd></div></dl>
        <p class="detail-note">{{ selectedKind==='gene'?'表达单位：':selectedKind==='reaction'?'反应单位：':'任务单位：' }}{{ trace?.score_units?.[selectedKind] || '请查阅本次运行来源' }}</p>
        <section v-if="coverage" class="coverage-detail"><h4>官方数据完整性</h4><strong>{{ fmtPercent(coverage.fraction_present_all,1) }}</strong><p>全部关联基因 {{ coverage.n_present_all }} / {{ coverage.n_genes_all }}</p><p>影响加权 {{ fmtPercent(coverage.impact_weighted_completeness_all,1) }}</p><details v-if="coverage.n_missing_all"><summary>缺失 {{ coverage.n_missing_all }} 个基因</summary><p class="mono">{{ coverage.missing_genes_all }}</p></details><small>覆盖率描述输入基因是否存在，不是预测置信度。</small></section>
        <p v-else-if="selectedKind!=='gene'" class="detail-note">{{ coverageError?'官方完整性读取失败：'+coverageError:official?'本节点未列入本次官方完整性报告。':entry?.tasks.data?.completeness_available?'正在读取官方完整性…':'本次未提供官方完整性。' }} <button v-if="coverageError" class="btn btn-sm" @click="loadCoverage">重试完整性</button></p>
        <section v-if="reaction" class="gpr-detail"><h4>当前反应的 GPR 规则</h4><code>{{ reaction.gene_rule || '本次记录未提供' }}</code><p>知识库基因与反应关联；不表示已证明的驱动基因。AND / OR 按原记录保留。</p><details><summary>全部关联基因（{{ reaction.genes.length }}）</summary><button v-for="gene in reaction.genes" :key="gene.id" class="gene-link" @click="choose('gene',gene.id)">{{ gene.label }} · Δ {{ fmtDelta(gene.predicted_delta,3) }}</button></details></section>
        <section class="provenance-detail"><h4>本次来源</h4><p class="mono">{{ runId }}</p><RouterLink v-if="entry?.provenance.data?.source_run_id" :to="{path:'/workbench',query:{run:entry.provenance.data.source_run_id,tab:'metabolism',view:'function'}}">原始真实运行：{{ entry.provenance.data.source_run_id }} ↗</RouterLink><p>{{ trace?.database_version || '知识库版本未提供' }}</p><details v-if="trace"><summary>冻结知识库哈希</summary><p class="mono">{{ trace.database_provenance.manifest_sha256 }}</p></details><RouterLink :to="{path:'/workbench',query:{run:runId,tab:'metabolism',view:'data'}}">完整代谢与覆盖结果 ↗</RouterLink><RouterLink :to="{path:'/workbench',query:{run:runId,tab:'validation'}}">本次预测验证 ↗</RouterLink></section>
      </aside>
    </div>
    <footer class="function-boundary">这是基于本次表达与 scCellFie 分数的功能关联视图。分数不等于代谢通量；网络布局不代表细胞空间位置。群体均值没有逐细胞配对，差值大小不代表统计显著性。未提供实测时，仅比较对照与模型预测。</footer>
  </section>
</template>
<style scoped>
.function-workspace{min-width:0}.function-heading{display:flex;justify-content:space-between;gap:20px;align-items:center;margin:25px 0}.function-heading h2{font-size:24px;font-weight:500;margin:10px 0}.function-heading p{font-size:12px;color:var(--muted);line-height:1.8}.function-heading .pill{white-space:normal;max-width:210px}.function-layout{display:grid;grid-template-columns:240px minmax(0,1fr) 260px;gap:16px;align-items:start}.task-browser,.function-main,.node-detail{border:1px solid var(--border);background:var(--card);padding:18px;min-width:0}h3{font-size:15px;font-weight:500;margin:0 0 10px}h4{font-size:13px;font-weight:500;line-height:1.7;margin:12px 0}.task-browser header p,.reaction-browser p{font-size:10px;color:var(--muted);line-height:1.7}.task-browser h3 small{font-size:10px;color:var(--muted)}label{display:block;color:var(--muted);font-size:10px;margin:12px 0}input,select{display:block;width:100%;min-width:0;margin-top:6px;padding:9px;border:1px solid var(--border);background:var(--card);color:var(--ink);font:11px var(--font)}.task-options{max-height:490px;overflow:auto;margin-top:16px}.task-option{display:block;width:100%;text-align:left;border:0;border-bottom:1px solid var(--border);padding:13px 10px;background:transparent;cursor:pointer;color:var(--ink)}.task-option span{display:block;font-size:11px;line-height:1.6}.task-option small{display:block;color:var(--muted);font-size:9px;margin:6px 0}.task-option strong{font:11px Consolas,monospace}.task-option.active{background:var(--surface-tint-selected);box-shadow:inset 3px 0 var(--primary)}.task-option:hover{background:var(--surface-tint-hover)}.negative{color:var(--delta-down)}.positive{color:var(--delta-up)}.scope-note{display:block;font-size:9px;color:var(--muted);margin-top:12px;line-height:1.8}.task-heading h3{font-size:18px;line-height:1.6;margin:10px 0}.task-heading p{font:10px Consolas,monospace;color:var(--muted);overflow-wrap:anywhere}.mode-controls{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}.export-trace{margin-left:auto}.network-caption,.color-note{font-size:10px;color:var(--muted);line-height:1.8}.network-comparison{display:grid;grid-template-columns:1fr 1fr;gap:12px}.network-comparison.single{grid-template-columns:1fr}.color-note i{display:inline-block;width:10px;height:10px;vertical-align:middle;margin:0 3px 0 10px;border:1px solid var(--border-strong)}.cool{background:var(--delta-down)}.warm{background:var(--delta-up)}.zero{background:var(--zero-bg)}.missing{background:var(--missing-bg);border-style:dashed!important}.network-message{min-height:250px;padding:60px 20px;text-align:center;background:var(--message-bg);color:var(--muted);font-size:12px;line-height:1.9}.reaction-browser{border-top:1px solid var(--border);margin-top:24px;padding-top:20px}.reaction-browser header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.reaction-browser header span{font-size:10px;color:var(--muted)}.reaction-options{display:flex;flex-wrap:wrap;gap:6px;max-height:210px;overflow:auto}.reaction-options .btn{font-size:10px}.reaction-options small{margin-left:6px}.node-detail .identifier{font-size:10px;color:var(--muted)}.node-scores{margin:20px 0}.node-scores div{display:flex;justify-content:space-between;gap:8px;border-bottom:1px solid var(--border);padding:12px 0}.node-scores dt{font-size:10px;color:var(--muted)}.node-scores dd{font:15px Consolas,monospace;margin:0}.detail-note,.coverage-detail p,.coverage-detail small,.gpr-detail p,.provenance-detail p{font-size:10px;line-height:1.9;color:var(--muted)}.node-detail section{border-top:1px solid var(--border);margin-top:18px;padding-top:4px}.coverage-detail strong{font:30px Georgia,serif;color:var(--primary)}.node-detail details{font-size:10px;line-height:1.8;margin:12px 0}.node-detail summary{cursor:pointer;color:var(--primary)}.node-detail code{display:block;font:11px Consolas,monospace;background:var(--code-bg);padding:12px;white-space:pre-wrap;overflow-wrap:anywhere}.node-detail p,.node-detail h4{overflow-wrap:anywhere}.gene-link{display:block;text-align:left;font:10px Consolas,monospace;padding:8px;border:0;border-bottom:1px solid var(--border);background:transparent;color:var(--primary);width:100%;cursor:pointer}.provenance-detail a{display:block;font-size:10px;line-height:2.4}.trace-notes{font-size:10px;color:var(--muted);line-height:1.9;margin-top:18px}.trace-notes summary{cursor:pointer;color:var(--primary)}.function-boundary{font-size:11px;line-height:2;color:var(--muted);border-top:1px solid var(--border);padding:18px 0;margin-top:22px}.task-browser :deep(.pager){gap:6px}.task-browser :deep(.pager span){flex-basis:100%;font-size:9px}@media(max-width:1450px){.function-layout{grid-template-columns:215px minmax(0,1fr)}.node-detail{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr 1fr;gap:0 24px}.node-detail>.eyebrow,.node-detail>h3,.node-detail>h4,.node-detail>.identifier{grid-column:1/-1}.node-detail section{margin-top:0}.node-scores{margin:0}}@media(max-width:1050px){.function-layout{grid-template-columns:1fr}.task-options{max-height:210px;display:grid;grid-template-columns:1fr 1fr}.task-browser{display:grid;grid-template-columns:1fr 1fr;gap:0 12px}.task-browser>header,.task-options,.task-browser>.scope-note{grid-column:1/-1}.task-browser label{margin:6px 0}.task-browser :deep(.pager){grid-column:1/-1}.node-detail{grid-template-columns:1fr 1fr}}@media(max-width:650px){.function-heading{display:block}.function-heading h2{font-size:21px}.function-heading .pill{max-width:none}.network-comparison{grid-template-columns:1fr}.node-detail{display:block}.node-detail section{margin-top:18px}.task-browser,.function-main,.node-detail{padding:14px}.task-heading h3{font-size:16px}.export-trace{margin-left:0}}
</style>
