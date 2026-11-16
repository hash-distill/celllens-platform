<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { apiFetch } from '../../api/http'
import { api } from '../../api/client'
import { isMockEnabled } from '../../api/mockFlag'
import type { ComparisonRow, MeasuredComparison } from '../../types/comparison'
import ValidationScatter from '../../charts/ValidationScatter.vue'
import { fmtNumber } from '../../utils/format'
import { downloadBlob } from '../../utils/csv'
import { taskName } from '../../utils/biologyLocale'

const props = defineProps<{runId: string}>()
const data = ref<MeasuredComparison | null>(null)
const loading = ref(false), error = ref(''), downloadError = ref('')
const search = ref(''), view = ref<'genes'|'tasks'>('genes'), chosen = ref('')
const downloading = ref(false)
const preparing = ref(false), preparationError = ref(''), showAllTasks = ref(false)
let controller: AbortController | null = null
let downloadController: AbortController | undefined
let retryTimer: ReturnType<typeof setTimeout> | undefined
let prepareController: AbortController | undefined
async function load() {
  clearTimeout(retryTimer)
  controller?.abort()
  downloadController?.abort();downloading.value=false;downloadError.value=''
  const current = new AbortController()
  controller = current
  data.value = null; error.value = ''; loading.value = true
  try {
    if (isMockEnabled()) throw new Error('合成示例不提供实测比较，请选择真实分析结果。')
    const result = await apiFetch<MeasuredComparison>(`/runs/${encodeURIComponent(props.runId)}/comparison`, {signal: current.signal, timeoutMs: 120000})
    if (!current.signal.aborted) {
      data.value = result
      if(result.status==='preparing') retryTimer=setTimeout(() => void load(),5000)
    }
  } catch (e) {
    if (!current.signal.aborted) error.value = e instanceof Error ? e.message : '实测比较读取失败'
  } finally { if (!current.signal.aborted) loading.value = false }
}
watch(() => props.runId, () => {prepareController?.abort(); preparing.value=false; preparationError.value=''; search.value=''; chosen.value=''; view.value='genes'; showAllTasks.value=false; void load()}, {immediate:true})
onBeforeUnmount(() => {controller?.abort();downloadController?.abort(); prepareController?.abort(); clearTimeout(retryTimer)})
const rows = computed(() => (data.value?.[view.value] ?? []).filter(row => view.value!=='tasks' || showAllTasks.value || row.evidence_level==='supported'))
const pairs = computed(() => rows.value.map(row => ({name:row.id, predicted:row.predicted_delta, observed:row.observed_delta})))
const ranked = computed(() => [...rows.value].sort((a,b) => view.value==='tasks'
  ? a.id.localeCompare(b.id)
  : Math.max(Math.abs(b.predicted_delta),Math.abs(b.observed_delta))-Math.max(Math.abs(a.predicted_delta),Math.abs(a.observed_delta))))
const visible = computed(() => ranked.value.filter(row => `${row.id} ${view.value==='tasks'?taskName(row.id):''}`.toLowerCase().includes(search.value.trim().toLowerCase())).slice(0,30))
const selected = computed(() => rows.value.find(row => row.id===chosen.value) ?? visible.value[0])
const expression = computed(() => data.value?.expression)
const ratio = computed(() => typeof expression.value?.mse_relative_to_no_change==='number' ? expression.value.mse_relative_to_no_change : null)
const population = computed(() => data.value?.parameters?.population_counts)
const sensitivity = computed(() => data.value?.batch_sensitivity)
const coverage = computed(() => data.value?.task_coverage)
const stratumNote = '分层相关系数仅为描述性诊断；尤其只有 2 个任务时 ±1 不构成强证据。不同任务也可能共享输入基因，不能按独立样本解释。'
const evidenceLabels: Record<string, string> = {supported:'较高覆盖（≥80%）', exploratory:'探索性（60%–<80%）', insufficient:'覆盖不足（<60%）', unknown:'覆盖未知'}
const baselineLabel = computed(() => sensitivity.value?.baseline_conclusion_consistent===false
  ? '基线结论依赖批次权重'
  : sensitivity.value?.status==='available' && sensitivity.value.baseline_conclusion_consistent===true
    ? '原汇总估计与批次等权诊断方向一致；仍为本案例诊断'
    : sensitivity.value?.status==='available' ? sensitivity.value.baseline_comparison_reason ?? '基线误差比未定义'
    : '原汇总估计；尚未检验批次权重敏感性')
const expressionCards = computed(() => [
  {label:'变化 Pearson',value:expression.value?.signed_delta_pearson,note:'−1 至 1；线性趋势一致性，需结合 MSE 阅读'},
  {label:'变化 Spearman',value:expression.value?.signed_delta_spearman,note:'比较变化排序的一致性'},
  {label:'预测变化 MSE',value:expression.value?.mse,note:'与实测变化的均方误差；越低越好'},
  {label:'MSE / 不变化基线',value:ratio.value,note:'原汇总估计；小于 1 表示此权重下误差较低，需结合批次敏感性'},
])
const deLabels = {observed_significant_genes:'实测诊断显著 DEG',predicted_significant_genes:'预测诊断显著 DEG',shared_significant_genes:'共有诊断显著 DEG',overlap_at_n:'DE Overlap@N',average_precision:'DE 平均精确率 AP',direction_agreement_on_shared_degs:'共有诊断显著 DEG 方向一致率'}
function number(value: unknown) {return fmtNumber(typeof value==='number'?value:null)}
async function prepareDiagnostics() {
  if(preparing.value) return
  const id=props.runId, current=prepareController=new AbortController()
  preparing.value=true; preparationError.value=''
  try {
    const result=await apiFetch<MeasuredComparison>(`/runs/${encodeURIComponent(id)}/comparison/diagnostics/prepare`, {method:'POST', signal:current.signal, timeoutMs:120000})
    if(!current.signal.aborted && props.runId===id) data.value=result
  } catch(e) {if(!current.signal.aborted) preparationError.value=e instanceof Error?e.message:'诊断准备失败'}
  finally {if(!current.signal.aborted) preparing.value=false}
}
function values(row: ComparisonRow) {return [{label:'实测对照',value:row.control,kind:'control'},{label:'模型预测',value:row.predicted,kind:'predicted'},{label:'扰动后实测',value:row.observed,kind:'observed'}]}
async function download(table: 'json'|'genes'|'tasks') {
  if (downloading.value || isMockEnabled()) return
  const id = props.runId, current = downloadController = new AbortController()
  downloading.value=true;downloadError.value=''
  try {
    const result=await api.getComparisonDownload(id,table,current.signal)
    if(!current.signal.aborted && id===props.runId) downloadBlob(result.blob,result.filename)
  } catch(e) {if(!current.signal.aborted) downloadError.value=e instanceof Error?e.message:'下载失败'}
  finally {if(!current.signal.aborted) downloading.value=false}
}
</script>

<template>
  <section class="measured-comparison" aria-label="真实实测与模型预测比较">
    <header class="comparison-heading"><div><span class="eyebrow">MEASURED / PREDICTED</span><h2>让预测与真实测量对照</h2><p>同一细胞背景与基因扰动，比较相对于实测对照的变化。</p></div><button class="btn btn-sm" :disabled="loading" @click="load">{{loading?'读取中…':'刷新比较'}}</button></header>
    <div v-if="loading" class="comparison-empty" role="status">正在加载实测对比…</div>
    <div v-else-if="error" class="notice notice-warn" role="alert">{{error}}<p>请稍后重试。</p></div>
    <template v-else-if="data">
      <template v-if="data.status==='available'">
        <div class="source-strip"><span class="source-tag">真实 Perturb-seq RNA</span><strong>{{data.cell_line}} / {{data.perturbation}}</strong><span v-if="population">实测对照 {{population.control}} · 模型预测 {{population.predicted}} · 扰动后实测 {{population.observed}} 个细胞</span><a v-if="data.source?.url" :href="data.source.url" target="_blank" rel="noopener noreferrer">查看官方数据源 ↗</a></div>
        <p class="comparison-scope">比较同一背景、同一扰动下的实测对照、模型预测和扰动后实测。</p>
        <div class="metric-grid"><article v-for="card in expressionCards" :key="card.label" class="metric-card" :class="{worse:card.label==='MSE / 不变化基线' && ratio!==null && ratio>=1}"><h3>{{card.label}}</h3><strong>{{number(card.value)}}</strong><p>{{card.note}}</p></article></div>
        <div v-if="ratio!==null" class="baseline-note" :class="{worse:ratio>=1 || sensitivity?.baseline_conclusion_consistent===false}" data-baseline-result><strong>{{baselineLabel}}</strong><span>原汇总不变化 MSE {{number(expression?.no_change_mse)}}；变化 MAE {{number(expression?.mae)}}。</span></div>
        <section class="de-panel" aria-label="批次组成敏感性诊断"><h3>批次组成敏感性诊断</h3>
          <template v-if="sensitivity?.status==='available'"><p>{{sensitivity.formula}}</p><dl><div><dt>原细胞汇总误差比</dt><dd>{{number(sensitivity.pooled_cells?.mse_relative_to_no_change)}}</dd></div><div><dt>共同批次等权误差比</dt><dd>{{number(sensitivity.equal_batch_weight?.mse_relative_to_no_change)}}</dd></div><div><dt>对照 / 实测批次频率总变差</dt><dd>{{number(sensitivity.total_variation_control_observed)}}</dd></div></dl><p>使用相同基因轴与有限数值，已检查各来源内细胞 ID 无重复。gem_group 不是独立生物学重复；模拟预测记录不能增加实测证据。</p><details><summary>各共同批次的组成</summary><div class="paired-table-wrap"><table><thead><tr><th>批次</th><th>对照</th><th>预测</th><th>实测</th></tr></thead><tbody><tr v-for="batch in sensitivity.common_batches" :key="batch"><td>{{batch}}</td><td>{{sensitivity.batch_counts?.control?.[batch]}}</td><td>{{sensitivity.batch_counts?.predicted?.[batch]}}</td><td>{{sensitivity.batch_counts?.observed?.[batch]}}</td></tr></tbody></table></div></details><details><summary>敏感性诊断的解释范围</summary><p v-for="note in sensitivity.limitations" :key="note">{{note}}</p></details></template>
          <template v-else><p>{{sensitivity?.reason ?? '批次敏感性尚未显式准备；刷新仅读取已有结果。'}}</p><button class="btn btn-sm" :disabled="preparing || sensitivity?.status==='invalid'" @click="prepareDiagnostics">{{preparing?'正在核验已有矩阵并准备诊断…':'准备批次敏感性诊断'}}</button><p>仅重算已有矩阵均值并另存诊断，不重跑 STATE；原冻结指标保持不变。</p></template><p v-if="preparationError" role="alert">{{preparationError}}</p>
        </section>
        <div class="comparison-tools"><div class="view-toggle"><button class="btn btn-sm" :class="{'btn-primary':view==='genes'}" @click="view='genes'; chosen=''">基因表达比较</button><button class="btn btn-sm" :class="{'btn-primary':view==='tasks'}" @click="view='tasks'; chosen=''">代谢任务比较</button></div><button class="btn btn-sm" :disabled="downloading" @click="download(view)">下载完整{{view==='genes'?'基因':'任务'}}对比 CSV</button></div>
        <div v-if="view==='tasks'" class="comparison-tools"><p>任务分数由比较群体的表达经 scCellFie 派生，不是代谢通量。知识库 {{coverage?.knowledge_base_task_count ?? '未知'}} 项；具有有限数值的成对任务 {{coverage?.finite_paired_task_count ?? data.tasks?.length}} 项；未评分 {{coverage?.unscored_task_count ?? '未知'}} 项。较高覆盖（≥80%） {{coverage?.by_evidence_level.supported ?? 0}} / 探索性 {{coverage?.by_evidence_level.exploratory ?? 0}} / 覆盖不足 {{coverage?.by_evidence_level.insufficient ?? 0}}。</p><label><input v-model="showAllTasks" type="checkbox" @change="chosen=''" /> 展开覆盖不足、探索性与未知任务</label></div>
        <div class="comparison-grid"><article class="chart-panel"><div class="panel-heading"><h3>预测变化 × 实测变化</h3><span>当前展示 {{rows.length}} 个具有有限数值的成对{{view==='genes'?'基因':'任务'}}</span></div><p>虚线 y=x 表示数值一致；任务数量不是独立功能证据数量。</p><ValidationScatter v-if="pairs.length" :key="view" :pairs="pairs" :item-name="view==='genes'?'基因':'任务'"/><p v-else class="comparison-empty">当前覆盖筛选下没有可比较的已评分任务。</p></article>
          <article class="population-panel"><h3>{{selected ? (view==='tasks'?taskName(selected.id):selected.id) : '选择一个指标'}}</h3><small v-if="selected && view==='tasks' && taskName(selected.id)!==selected.id" class="task-identifier">{{selected.id}}</small><p>{{view==='genes'?'三组平均表达 · mean(log1p(CP10K))':'三组平均 scCellFie 任务分数'}}</p><template v-if="selected"><div v-for="item in values(selected)" :key="item.kind" class="population-value" :class="item.kind"><span>{{item.label}}</span><strong>{{number(item.value)}}</strong></div><dl class="paired-deltas"><dt>预测 − 对照</dt><dd>{{number(selected.predicted_delta)}}</dd><dt>实测 − 对照</dt><dd>{{number(selected.observed_delta)}}</dd><dt>变化绝对误差</dt><dd>{{number(selected.absolute_error)}}</dd></dl></template><p>比较三组的群体平均值。</p></article></div>
        <div class="paired-table-panel"><div class="panel-heading"><h3>逐项核对</h3><input v-model="search" :aria-label="view==='genes'?'搜索比较基因':'搜索比较任务'" :placeholder="view==='genes'?'搜索基因名称':'搜索任务名称'" /></div><p>{{view==='genes'?'基因按预测或实测变化幅度排列':'任务默认仅显示较高覆盖项（≥80%）；覆盖来自本次匹配比较的冻结面板'}}，显示匹配项前 30 条；完整记录可下载。</p><div class="paired-table-wrap"><table><thead><tr><th>{{view==='genes'?'基因':'代谢任务'}}</th><th>实测对照</th><th>预测</th><th>扰动后实测</th><th>预测变化</th><th>实测变化</th><th>绝对误差</th><th v-if="view==='tasks'">覆盖率 / 层级</th><th v-if="view==='tasks'">缺失基因 / 相同评分结构</th></tr></thead><tbody><tr v-for="row in visible" :key="row.id" :class="{selected:row.id===selected?.id}"><td><button @click="chosen=row.id">{{view==='tasks'?taskName(row.id):row.id}}</button><small v-if="view==='tasks' && taskName(row.id)!==row.id" class="task-identifier">{{row.id}}</small></td><td>{{number(row.control)}}</td><td>{{number(row.predicted)}}</td><td>{{number(row.observed)}}</td><td>{{number(row.predicted_delta)}}</td><td>{{number(row.observed_delta)}}</td><td>{{number(row.absolute_error)}}</td><td v-if="view==='tasks'">{{row.coverage==null?'未知':number(row.coverage*100)+'%'}} / {{evidenceLabels[row.evidence_level ?? 'unknown'] ?? row.evidence_level}}</td><td v-if="view==='tasks'" class="coverage-detail">{{row.coverage==null?'缺失列表未知':row.missing_genes || '无缺失基因'}}<br />{{row.same_score_structure_task_count ?? '尚未准备'}} 项共享该三元均值</td></tr><tr v-if="!visible.length"><td :colspan="view==='tasks'?9:7">没有匹配记录。</td></tr></tbody></table></div></div>
        <section v-if="view==='genes'" class="de-panel"><h3>差异表达：细胞级探索性诊断</h3><p><strong>非生物学重复检验。</strong>预测与实测分别对照真实对照，使用 Wilcoxon、tie correction、BH-FDR &lt; 0.05。增加模拟细胞数量不能增加实测的独立证据。</p><p>共有诊断显著 DEG / 实测诊断显著 DEG：<strong>{{data.differential_expression?.shared_significant_genes}} / {{data.differential_expression?.observed_significant_genes}}</strong>。方向一致率仅针对这 {{data.differential_expression?.shared_significant_genes}} 个共有基因，不代表全部基因正确率。</p><p>独立留出验证：{{data.held_out_validation?'已记录':'未建立'}}；训练排除：{{data.training_exclusion_verified?'已核验':'未核验'}}。</p><dl><template v-for="(label,key) in deLabels" :key="key"><div><dt>{{label}}</dt><dd>{{number(data.differential_expression?.[key])}}</dd></div></template></dl><p>Overlap@N 以实测诊断显著基因数 N 为分母，在各自诊断显著基因中按绝对 logFC 排序；AP 以实测诊断显著标签和预测调整 p 值排序计算。</p></section>
        <section v-else-if="data.metabolic" class="de-panel"><h3>表达派生任务的一致性</h3><p>以下为冻结的全部有限成对任务汇总，包含覆盖不足任务；不代表独立功能验证数量。</p><dl><div><dt>原汇总 Spearman</dt><dd>{{number(data.metabolic.spearman)}}</dd></div><div><dt>原汇总 MAE</dt><dd>{{number(data.metabolic.mae)}}</dd></div><div><dt>具有有限数值的成对任务数</dt><dd>{{number(data.metabolic.valid_task_count)}}</dd></div></dl><div v-if="coverage?.stratified_metrics" class="paired-table-wrap"><table><thead><tr><th>覆盖层级</th><th>有限成对任务</th><th>Spearman</th><th>MAE</th></tr></thead><tbody><tr v-for="(metrics, level) in coverage.stratified_metrics" :key="level"><td>{{evidenceLabels[level] ?? level}}</td><td>{{metrics.finite_paired_task_count}}</td><td>{{number(metrics.spearman)}}</td><td>{{number(metrics.mae)}}</td></tr></tbody></table><p>{{stratumNote}}</p><p>按 8 位小数有 {{coverage.distinct_mean_triplets_8dp}} 种不同三元均值。{{coverage.independence_note}}</p></div><p v-else>覆盖分层数量已展示；分层指标与重复评分结构需显式准备诊断。</p></section>
        <section class="comparison-provenance"><h3>评价总体与解释边界</h3><p>{{data.evaluation_protocol?.comparison_policy}}</p><p>参考群体选择指纹：<code>{{data.evaluation_protocol?.reference_selection_sha256 ?? '尚未准备，不能认定跨运行评价总体一致'}}</code></p><details><summary>展开完整解释边界</summary><p v-for="warning in data.warnings_zh" :key="warning">{{warning}}</p></details></section>
        <details class="comparison-provenance"><summary>数据来源与指标说明</summary><p>来源：{{data.source?.repo}}；数据版本：<code>{{data.source?.revision}}</code></p><p>比较 SHA-256：<code>{{data.comparison_sha256}}</code>；实测输入 SHA-256：<code>{{data.source?.observed_sha256}}</code></p><p v-if="data.population_matching">输入细胞数：对照 {{data.population_matching.input_cells.control}} / 预测 {{data.population_matching.input_cells.predicted}} / 实测 {{data.population_matching.input_cells.observed}}；共有批次 {{data.population_matching.common_batches.length}} 个。</p><p v-for="source in data.metric_sources" :key="source.url"><a :href="source.url" target="_blank" rel="noopener noreferrer">{{source.label}} ↗</a> · {{source.scope}}</p><button class="btn btn-sm" :disabled="downloading" @click="download('json')">下载指标、成对数据与来源 JSON</button></details>
      </template>
      <div v-else class="comparison-empty" data-comparison-unavailable><span class="eyebrow">{{data.status==='preparing'?'PREPARING COMPARISON':'MEASUREMENT UNAVAILABLE'}}</span><h3>{{data.cell_line}} / {{data.perturbation}} {{data.status==='preparing'?'实测比较准备中':'暂无实测对比'}}</h3><p>{{data.reason}}</p><p v-if="data.available_measured_cells===0">当前数据集中暂无匹配的实测细胞。</p><a v-if="data.source?.url" :href="data.source.url" target="_blank" rel="noopener noreferrer">查看官方数据源 ↗</a></div>
      <section v-if="data.examples.length" class="comparison-examples"><h3>查看其他实测对比</h3><div><RouterLink v-for="item in data.examples" :key="item.run_id" :to="{path:'/demo',query:{run:item.run_id,tab:'comparison'}}">{{item.cell_line}} / {{item.perturbation}} ↗</RouterLink></div></section>
    </template>
    <p v-if="downloadError" class="notice notice-warn" role="alert">{{downloadError}}</p>
  </section>
</template>

<style scoped>
.coverage-detail{max-width:280px;min-width:160px;white-space:normal;overflow-wrap:anywhere}.comparison-tools label{font-size:12px}.de-panel{margin-bottom:16px}
.comparison-heading,.panel-heading,.comparison-tools{display:flex;justify-content:space-between;gap:16px;align-items:center}.comparison-heading{margin-bottom:22px}.eyebrow{font-size:10px;letter-spacing:.12em;color:var(--primary)}h2{font-size:24px;font-weight:500;margin:10px 0}h3{font-size:14px;font-weight:500;margin:0 0 10px}p{font-size:11px;color:var(--muted);line-height:1.9;margin:8px 0}.source-strip{display:flex;align-items:center;gap:14px;flex-wrap:wrap;background:var(--panel-alt,var(--card));padding:16px;border:1px solid var(--border);font-size:11px}.source-tag{color:var(--primary);font-size:10px}.source-strip a{margin-left:auto}.comparison-scope{margin-bottom:22px}.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.metric-card{padding:20px 18px;background:var(--card);border:1px solid var(--border)}.metric-card h3{font-size:11px;color:var(--muted)}.metric-card>strong{font:500 28px Georgia,serif;color:var(--primary);display:block;padding:8px 0}.metric-card.worse>strong{color:#a66b32}.metric-card p{font-size:10px;min-height:36px}.baseline-note{padding:16px 18px;border-left:3px solid var(--primary);background:var(--card);margin:14px 0 24px;display:flex;gap:18px;flex-wrap:wrap;font-size:11px}.baseline-note.worse{border-left-color:#b4753a}.baseline-note span{color:var(--muted)}.comparison-tools{margin:24px 0 16px;flex-wrap:wrap}.comparison-grid{display:grid;grid-template-columns:minmax(0,1.8fr) minmax(240px,1fr);gap:16px}.chart-panel,.population-panel,.paired-table-panel,.de-panel{padding:20px;border:1px solid var(--border);background:var(--card);min-width:0}.panel-heading span{font-size:10px;color:var(--muted)}.population-value{display:flex;justify-content:space-between;padding:18px 12px;border-left:3px solid #9aa5b1;background:var(--bg);margin:12px 0;font-size:12px}.population-value.predicted{border-color:#79b7b2}.population-value.observed{border-color:#c7a45e}.population-value strong{font-variant-numeric:tabular-nums}.paired-deltas{display:grid;grid-template-columns:1fr auto;gap:12px;font-size:11px;margin:25px 0}.paired-deltas dd{margin:0}.paired-deltas dt{color:var(--muted)}.paired-table-panel{margin:16px 0}.panel-heading input{max-width:260px;min-width:0}.paired-table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:11px;font-variant-numeric:tabular-nums;white-space:nowrap}th,td{text-align:right;padding:12px 9px;border-bottom:1px solid var(--border)}th:first-child,td:first-child{text-align:left}td button{color:var(--primary);background:none;border:0;cursor:pointer;max-width:310px;text-align:left;white-space:normal;font:inherit}tr.selected{background:var(--bg)}.de-panel dl{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.de-panel dt{font-size:11px;color:var(--muted)}.de-panel dd{margin:10px 0;font-size:19px}.comparison-provenance{margin:16px 0;border:1px solid var(--border);padding:16px;font-size:12px}.comparison-provenance summary{cursor:pointer;color:var(--primary)}code{font-size:10px;overflow-wrap:anywhere}.comparison-empty{text-align:center;padding:48px 20px;border:1px solid var(--border);background:var(--card)}.comparison-empty h3{font-size:19px;margin:15px 0}.comparison-examples{margin-top:24px}.comparison-examples>div{display:flex;gap:10px;flex-wrap:wrap}.comparison-examples a{padding:10px 14px;border:1px solid var(--border);background:var(--card);font-size:11px}.notice{margin-top:16px}

/* Keep numerical comparisons readable without widening the document on small screens. */
.measured-comparison{min-width:0}
p,.comparison-scope{font-size:13px}
.metric-card h3,.metric-card p,.source-strip,.baseline-note,.paired-deltas,.de-panel dt{font-size:12px}
.metric-grid{grid-template-columns:repeat(4,minmax(0,1fr))}
.metric-card{min-width:0;overflow-wrap:anywhere}
.source-strip,.comparison-heading>div,.panel-heading{min-width:0}
.paired-table-wrap{max-width:100%}
table{font-size:12px}
.task-identifier{display:block;max-width:310px;margin-top:5px;color:var(--muted);font-size:11px;line-height:1.6;white-space:normal;overflow-wrap:anywhere}
.population-panel h3{line-height:1.6}
.de-panel summary,.comparison-provenance summary{cursor:pointer;color:var(--primary);font-size:12px;line-height:1.8}
.de-panel details{margin-top:10px}
@media(max-width:800px){
 .metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
 .comparison-grid{grid-template-columns:minmax(0,1fr)}
 .comparison-heading,.panel-heading{align-items:flex-start;flex-wrap:wrap}
 .source-strip a{margin-left:0}
 .de-panel dl{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media(max-width:480px){
 .chart-panel,.population-panel,.paired-table-panel,.de-panel{padding:14px}
 .metric-card{padding:14px 12px}
 .metric-card>strong{font-size:25px}
 .de-panel dl{grid-template-columns:minmax(0,1fr)}
 .source-strip{gap:8px;padding:12px}
 .panel-heading input{width:100%;max-width:none}
 .baseline-note{gap:8px}
}
</style>
