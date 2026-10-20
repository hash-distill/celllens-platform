<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { apiFetch, apiUrl } from '../../api/http'
import { isMockEnabled } from '../../api/mockFlag'
import type { ComparisonRow, MeasuredComparison } from '../../types/comparison'
import ValidationScatter from '../../charts/ValidationScatter.vue'
import { fmtNumber } from '../../utils/format'
import { downloadBlob } from '../../utils/csv'

const props = defineProps<{runId: string}>()
const data = ref<MeasuredComparison | null>(null)
const loading = ref(false), error = ref(''), downloadError = ref('')
const search = ref(''), view = ref<'genes'|'tasks'>('genes'), chosen = ref('')
let controller: AbortController | null = null
let retryTimer: ReturnType<typeof setTimeout> | undefined
async function load() {
  clearTimeout(retryTimer)
  controller?.abort()
  const current = new AbortController()
  controller = current
  data.value = null; error.value = ''; loading.value = true
  try {
    if (isMockEnabled()) throw new Error('开发数据不提供实测比较，请切换到真实服务。')
    const result = await apiFetch<MeasuredComparison>(`/runs/${encodeURIComponent(props.runId)}/comparison`, {signal: current.signal, timeoutMs: 120000})
    if (!current.signal.aborted) {
      data.value = result
      if(result.status==='preparing') retryTimer=setTimeout(() => void load(),5000)
    }
  } catch (e) {
    if (!current.signal.aborted) error.value = e instanceof Error ? e.message : '实测比较读取失败'
  } finally { if (!current.signal.aborted) loading.value = false }
}
watch(() => props.runId, () => {search.value=''; chosen.value=''; view.value='genes'; void load()}, {immediate:true})
onBeforeUnmount(() => {controller?.abort(); clearTimeout(retryTimer)})
const rows = computed(() => data.value?.[view.value] ?? [])
const pairs = computed(() => rows.value.map(row => ({name:row.id, predicted:row.predicted_delta, observed:row.observed_delta})))
const ranked = computed(() => [...rows.value].sort((a,b) => Math.max(Math.abs(b.predicted_delta),Math.abs(b.observed_delta))-Math.max(Math.abs(a.predicted_delta),Math.abs(a.observed_delta))))
const visible = computed(() => ranked.value.filter(row => row.id.toLowerCase().includes(search.value.trim().toLowerCase())).slice(0,30))
const selected = computed(() => rows.value.find(row => row.id===chosen.value) ?? visible.value[0])
const expression = computed(() => data.value?.expression)
const ratio = computed(() => typeof expression.value?.mse_relative_to_no_change==='number' ? expression.value.mse_relative_to_no_change : null)
const population = computed(() => data.value?.parameters?.population_counts)
const expressionCards = computed(() => [
  {label:'变化 Pearson',value:expression.value?.signed_delta_pearson,note:'−1 至 1；线性趋势一致性，需结合 MSE 阅读'},
  {label:'变化 Spearman',value:expression.value?.signed_delta_spearman,note:'比较变化排序的一致性'},
  {label:'预测变化 MSE',value:expression.value?.mse,note:'与实测变化的均方误差；越低越好'},
  {label:'MSE / 不变化基线',value:ratio.value,note:'小于 1：优于“扰动后保持对照不变”'},
])
const deLabels = {observed_significant_genes:'实测显著 DEG',predicted_significant_genes:'预测显著 DEG',shared_significant_genes:'共有显著 DEG',overlap_at_n:'DE Overlap@N',average_precision:'DE 平均精确率 AP',direction_agreement_on_shared_degs:'共有显著 DEG 方向一致率'}
function number(value: unknown) {return fmtNumber(typeof value==='number'?value:null)}
function values(row: ComparisonRow) {return [{label:'实测对照',value:row.control,kind:'control'},{label:'模型预测',value:row.predicted,kind:'predicted'},{label:'扰动后实测',value:row.observed,kind:'observed'}]}
async function download(table: 'json'|'genes'|'tasks') {
  downloadError.value=''
  try {
    const response=await fetch(apiUrl(`/runs/${encodeURIComponent(props.runId)}/comparison/download`,{table}))
    if(!response.ok) throw new Error(`下载失败：HTTP ${response.status}`)
    downloadBlob(await response.blob(),`${props.runId}_measured_comparison_${table}.${table==='json'?'json':'csv'}`)
  } catch(e) {downloadError.value=e instanceof Error?e.message:'下载失败'}
}
</script>

<template>
  <section class="measured-comparison" aria-label="真实实测与模型预测比较">
    <header class="comparison-heading"><div><span class="eyebrow">MEASURED / PREDICTED</span><h2>让预测与真实测量对照</h2><p>同一细胞背景与基因扰动，比较相对于实测对照的变化。</p></div><button class="btn btn-sm" :disabled="loading" @click="load">{{loading?'读取中…':'刷新比较'}}</button></header>
    <div v-if="loading" class="comparison-empty" role="status">正在核验实测来源与预测文件…</div>
    <div v-else-if="error" class="notice notice-warn" role="alert">{{error}}<p>无法核验时停止展示；请重试读取。</p></div>
    <template v-else-if="data">
      <template v-if="data.status==='available'">
        <div class="source-strip"><span class="source-tag">真实 Perturb-seq RNA</span><strong>{{data.cell_line}} / {{data.perturbation}}</strong><span v-if="population">实测对照 {{population.control}} · 模型预测 {{population.predicted}} · 扰动后实测 {{population.observed}} 个细胞</span><a v-if="data.source?.url" :href="data.source.url" target="_blank" rel="noopener noreferrer">查看官方数据源 ↗</a></div>
        <p class="comparison-scope">采用三组共有的原始批次，保留各批次原有频率；非配对群体比较。此处的评价子集可能小于原实验展示的细胞数。</p>
        <div class="metric-grid"><article v-for="card in expressionCards" :key="card.label" class="metric-card" :class="{worse:card.label==='MSE / 不变化基线' && ratio!==null && ratio>=1}"><h3>{{card.label}}</h3><strong>{{number(card.value)}}</strong><p>{{card.note}}</p></article></div>
        <div v-if="ratio!==null" class="baseline-note" :class="{worse:ratio>=1}" data-baseline-result><strong>{{ratio<1?'本案例误差低于不变化基线':'本案例未优于不变化基线'}}</strong><span>不变化 MSE {{number(expression?.no_change_mse)}}；变化 MAE {{number(expression?.mae)}}。该结论仅适用于本次匹配观测。</span></div>
        <div class="comparison-tools"><div class="view-toggle"><button class="btn btn-sm" :class="{'btn-primary':view==='genes'}" @click="view='genes'; chosen=''">基因表达比较</button><button class="btn btn-sm" :class="{'btn-primary':view==='tasks'}" @click="view='tasks'; chosen=''">代谢任务比较</button></div><button class="btn btn-sm" @click="download(view)">下载完整{{view==='genes'?'基因':'任务'}}对比 CSV</button></div>
        <p v-if="view==='tasks'" class="notice notice-info">两组任务分数分别由预测 RNA、实测 RNA 经同一 scCellFie 流程计算；这不是实测代谢通量。基因覆盖不足仍会限制解释。</p>
        <div class="comparison-grid"><article class="chart-panel"><div class="panel-heading"><h3>预测变化 × 实测变化</h3><span>{{rows.length}} 个完整成对{{view==='genes'?'基因':'任务'}}</span></div><p>虚线 y=x 表示数值一致。全部有效成对记录均参与计算，包含零变化；没有按结果好坏筛选。</p><ValidationScatter v-if="pairs.length" :key="view" :pairs="pairs" :item-name="view==='genes'?'基因':'任务'"/><p v-else class="comparison-empty">本次没有可比较的已评分任务。</p></article>
          <article class="population-panel"><h3>{{selected?.id ?? '选择一个指标'}}</h3><p>{{view==='genes'?'三组平均表达 · mean(log1p(CP10K))':'三组平均 scCellFie 任务分数'}}</p><template v-if="selected"><div v-for="item in values(selected)" :key="item.kind" class="population-value" :class="item.kind"><span>{{item.label}}</span><strong>{{number(item.value)}}</strong></div><dl class="paired-deltas"><dt>预测 − 对照</dt><dd>{{number(selected.predicted_delta)}}</dd><dt>实测 − 对照</dt><dd>{{number(selected.observed_delta)}}</dd><dt>变化绝对误差</dt><dd>{{number(selected.absolute_error)}}</dd></dl></template><p>这些是非配对群体均值，不能把预测细胞与实测细胞逐一对应。</p></article></div>
        <div class="paired-table-panel"><div class="panel-heading"><h3>逐项核对</h3><input v-model="search" :aria-label="view==='genes'?'搜索比较基因':'搜索比较任务'" :placeholder="view==='genes'?'搜索基因名称':'搜索任务名称'" /></div><p>默认按预测或实测变化幅度排列，显示匹配项前 30 条；完整记录可下载。</p><div class="paired-table-wrap"><table><thead><tr><th>{{view==='genes'?'基因':'代谢任务'}}</th><th>实测对照</th><th>预测</th><th>扰动后实测</th><th>预测变化</th><th>实测变化</th><th>绝对误差</th></tr></thead><tbody><tr v-for="row in visible" :key="row.id" :class="{selected:row.id===selected?.id}"><td><button @click="chosen=row.id">{{row.id}}</button></td><td>{{number(row.control)}}</td><td>{{number(row.predicted)}}</td><td>{{number(row.observed)}}</td><td>{{number(row.predicted_delta)}}</td><td>{{number(row.observed_delta)}}</td><td>{{number(row.absolute_error)}}</td></tr><tr v-if="!visible.length"><td colspan="7">没有匹配记录。</td></tr></tbody></table></div></div>
        <section v-if="view==='genes'" class="de-panel"><h3>差异表达诊断</h3><p>预测与实测分别对照真实对照，使用 Wilcoxon、tie correction、BH-FDR &lt; 0.05。细胞级检验不替代独立生物学重复。</p><dl><template v-for="(label,key) in deLabels" :key="key"><div><dt>{{label}}</dt><dd>{{number(data.differential_expression?.[key])}}</dd></div></template></dl><p>Overlap@N 以实测显著基因数 N 为分母，在各自显著基因中按绝对 logFC 排序；AP 以实测显著标签和预测调整 p 值排序计算。它们是本项目固定实现，非完整官方评测分数。</p></section>
        <section v-else-if="data.metabolic" class="de-panel"><h3>表达派生任务的一致性</h3><dl><div><dt>Spearman</dt><dd>{{number(data.metabolic.spearman)}}</dd></div><div><dt>MAE</dt><dd>{{number(data.metabolic.mae)}}</dd></div><div><dt>有效任务数</dt><dd>{{number(data.metabolic.valid_task_count)}}</dd></div></dl></section>
        <details class="comparison-provenance"><summary>数据来源、指标定义与评价边界</summary><p>来源：{{data.source?.repo}}；固定版本：<code>{{data.source?.revision}}</code></p><p>实测文件 SHA-256：<code>{{data.source?.observed_sha256}}</code></p><p>原预测 SHA-256：<code>{{data.binding?.prediction_sha256}}</code></p><p v-if="data.population_matching">输入细胞数：对照 {{data.population_matching.input_cells.control}} / 预测 {{data.population_matching.input_cells.predicted}} / 实测 {{data.population_matching.input_cells.observed}}；共有批次 {{data.population_matching.common_batches.length}} 个。</p><p v-for="source in data.metric_sources" :key="source.url"><a :href="source.url" target="_blank" rel="noopener noreferrer">{{source.label}} ↗</a> · {{source.scope}}</p><button class="btn btn-sm" @click="download('json')">下载指标、成对数据与来源 JSON</button></details>
        <p class="notice notice-warn">本页为匹配实测诊断，检查点训练排除关系尚未核实。相近结果支持本案例的一致性，不足以证明未见扰动泛化、因果效应或实测代谢功能。</p>
      </template>
      <div v-else class="comparison-empty" data-comparison-unavailable><span class="eyebrow">{{data.status==='preparing'?'PREPARING COMPARISON':'MEASUREMENT UNAVAILABLE'}}</span><h3>{{data.cell_line}} / {{data.perturbation}} {{data.status==='preparing'?'实测比较准备中':'暂无实测对比'}}</h3><p>{{data.reason}}</p><p v-if="data.available_measured_cells===0">该固定数据版本中的匹配测量数为 0，不能据此推断模型准确率。</p><a v-if="data.source?.url" :href="data.source.url" target="_blank" rel="noopener noreferrer">核对官方数据源 ↗</a></div>
      <section v-if="data.examples.length" class="comparison-examples"><h3>查看已有真实对比</h3><div><RouterLink v-for="item in data.examples" :key="item.run_id" :to="{path:'/demo',query:{run:item.run_id,tab:'comparison'}}">{{item.cell_line}} / {{item.perturbation}} ↗</RouterLink></div></section>
    </template>
    <p v-if="downloadError" class="notice notice-warn" role="alert">{{downloadError}}</p>
  </section>
</template>

<style scoped>
.comparison-heading,.panel-heading,.comparison-tools{display:flex;justify-content:space-between;gap:16px;align-items:center}.comparison-heading{margin-bottom:22px}.eyebrow{font-size:10px;letter-spacing:.12em;color:var(--primary)}h2{font-size:24px;font-weight:500;margin:10px 0}h3{font-size:14px;font-weight:500;margin:0 0 10px}p{font-size:11px;color:var(--muted);line-height:1.9;margin:8px 0}.source-strip{display:flex;align-items:center;gap:14px;flex-wrap:wrap;background:var(--panel-alt,var(--card));padding:16px;border:1px solid var(--border);font-size:11px}.source-tag{color:var(--primary);font-size:10px}.source-strip a{margin-left:auto}.comparison-scope{margin-bottom:22px}.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.metric-card{padding:20px 18px;background:var(--card);border:1px solid var(--border)}.metric-card h3{font-size:11px;color:var(--muted)}.metric-card>strong{font:500 28px Georgia,serif;color:var(--primary);display:block;padding:8px 0}.metric-card.worse>strong{color:#a66b32}.metric-card p{font-size:10px;min-height:36px}.baseline-note{padding:16px 18px;border-left:3px solid var(--primary);background:var(--card);margin:14px 0 24px;display:flex;gap:18px;flex-wrap:wrap;font-size:11px}.baseline-note.worse{border-left-color:#b4753a}.baseline-note span{color:var(--muted)}.comparison-tools{margin:24px 0 16px;flex-wrap:wrap}.comparison-grid{display:grid;grid-template-columns:minmax(0,1.8fr) minmax(240px,1fr);gap:16px}.chart-panel,.population-panel,.paired-table-panel,.de-panel{padding:20px;border:1px solid var(--border);background:var(--card);min-width:0}.panel-heading span{font-size:10px;color:var(--muted)}.population-value{display:flex;justify-content:space-between;padding:18px 12px;border-left:3px solid #9aa5b1;background:var(--bg);margin:12px 0;font-size:12px}.population-value.predicted{border-color:#79b7b2}.population-value.observed{border-color:#c7a45e}.population-value strong{font-variant-numeric:tabular-nums}.paired-deltas{display:grid;grid-template-columns:1fr auto;gap:12px;font-size:11px;margin:25px 0}.paired-deltas dd{margin:0}.paired-deltas dt{color:var(--muted)}.paired-table-panel{margin:16px 0}.panel-heading input{max-width:260px;min-width:0}.paired-table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:11px;font-variant-numeric:tabular-nums;white-space:nowrap}th,td{text-align:right;padding:12px 9px;border-bottom:1px solid var(--border)}th:first-child,td:first-child{text-align:left}td button{color:var(--primary);background:none;border:0;cursor:pointer;max-width:310px;text-align:left;white-space:normal;font:inherit}tr.selected{background:var(--bg)}.de-panel dl{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.de-panel dt{font-size:11px;color:var(--muted)}.de-panel dd{margin:10px 0;font-size:19px}.comparison-provenance{margin:16px 0;border:1px solid var(--border);padding:16px;font-size:12px}.comparison-provenance summary{cursor:pointer;color:var(--primary)}code{font-size:10px;overflow-wrap:anywhere}.comparison-empty{text-align:center;padding:48px 20px;border:1px solid var(--border);background:var(--card)}.comparison-empty h3{font-size:19px;margin:15px 0}.comparison-examples{margin-top:24px}.comparison-examples>div{display:flex;gap:10px;flex-wrap:wrap}.comparison-examples a{padding:10px 14px;border:1px solid var(--border);background:var(--card);font-size:11px}.notice{margin-top:16px}
</style>
