<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../../api/client'
import { useRunStore } from '../../stores/run'
import { downloadBlob } from '../../utils/csv'
import { fmtNumber, fmtDelta } from '../../utils/format'
import { runSourceLabel } from '../../utils/source'
import type { PointSource } from '../../types/run'
import type { ScientificCellState } from '../../types/cellState'
import { hasPredictionChange } from '../../utils/predictionEvidence'
import { taskName } from '../../utils/biologyLocale'
import { featureFilenameToken } from '../../utils/download'
import { openAssistant, useAssistantFigure } from '../../stores/assistantSource'
const props = withDefaults(defineProps<{ runId: string; embedding?: 'pca'|'umap'; space?: 'expression'|'metabolic'; featureKind?: 'gene'|'task'; featureId?: string }>(), {embedding:'pca',space:'expression'})
const isUmap = computed(() => props.embedding === 'umap')
const isMetabolic = computed(() => props.space === 'metabolic')
const spaceLabel = computed(() => isMetabolic.value ? '代谢任务' : '表达')
const route = useRoute(), router = useRouter(), runs = useRunStore()
const record = computed(() => runs.entry(props.runId)?.record)
const data = ref<ScientificCellState | null>(null), figureUrl = ref(''), error = ref(''), exportError = ref('')
const loading = ref(false), exporting = ref(false), zoom = ref(false), search = ref('')
const kind = computed<'gene'|'task'>(() => props.featureKind ?? (route.query.feature_kind === 'task' ? 'task' : 'gene'))
const requestedFeature = computed(() => props.featureId ?? (typeof route.query.feature_id === 'string' ? route.query.feature_id : ''))
const options = computed(() => {
  const entry = runs.entry(props.runId)
  const eligible = new Set(kind.value === 'gene' ? entry?.genes.data?.items.filter(hasPredictionChange).map(row => row.gene) : entry?.tasks.data?.items.filter(hasPredictionChange).map(row => row.id))
  return ((kind.value === 'gene' ? data.value?.available_features.genes : data.value?.available_features.tasks) ?? []).filter(id => eligible.has(id))
})
const filtered = computed(() => options.value.filter(id => id === data.value?.feature.id || `${id} ${kind.value === 'task' ? taskName(id) : ''}`.toLowerCase().includes(search.value.toLowerCase().trim())))
const sourceLabels: Record<PointSource,string> = {control:'扰动前 / 对照',predicted:'扰动后 / 模型预测',observed:'扰动后 / 实测'}
const sourceColors: Record<PointSource,string> = {control:'#0072B2',predicted:'#D55E00',observed:'#009E73'}
const sources = computed(() => (['control','predicted','observed'] as PointSource[]).filter(source => data.value?.distributions[source]))
useAssistantFigure(() => data.value && figureUrl.value && !loading.value && !error.value ? {
  view:'chart',embedding:props.embedding,space:props.space,
  feature_kind:data.value.feature.kind,feature_id:data.value.feature.id,
} : null)
let controller: AbortController | undefined, exportController: AbortController | undefined
function clearFigure() { if (figureUrl.value) URL.revokeObjectURL(figureUrl.value); figureUrl.value = '' }
async function load() {
  controller?.abort(); exportController?.abort(); exporting.value = false
  const current = controller = new AbortController(), id = props.runId, chosenKind = kind.value, embedding = props.embedding
  clearFigure(); data.value = null; error.value = ''; exportError.value = ''; loading.value = true
  try {
    const entry = runs.entry(id)
    if (chosenKind === 'gene' && entry?.genes.status === 'idle') await runs.loadGenes(id)
    if (chosenKind === 'task' && entry?.tasks.status === 'idle') await runs.loadTasks(id)
    if (current.signal.aborted) return
    const document = await api.getCellState(id, chosenKind, requestedFeature.value, current.signal, embedding, props.space)
    if (current.signal.aborted) return
    if (embedding === 'umap' && document.method !== 'joint-umap') throw new Error('当前服务尚未启用 UMAP，请重启分析服务后重试。')
    if (props.space === 'metabolic' && document.embedding_space !== 'metabolic') throw new Error('当前服务尚未启用代谢任务空间，请重新启动分析服务后重试。')
    const control = document.distributions.control?.mean, predicted = document.distributions.predicted?.mean
    if (!hasPredictionChange({control,predicted,predicted_delta:control != null && predicted != null ? predicted-control : null}) || Object.values(document.distributions).some(group => group && group.n_valid !== group.n)) throw new Error('该指标暂不可用，请选择其他指标。')
    data.value = document
    const figure = await api.getCellStateFigure(id, document.feature.kind, document.feature.id, 'svg', current.signal, embedding, props.space)
    if (!current.signal.aborted) figureUrl.value = URL.createObjectURL(figure.blob)
  } catch (cause) { if (!current.signal.aborted) error.value = cause instanceof Error ? cause.message : '科研图读取失败' }
  finally { if (!current.signal.aborted) loading.value = false }
}
watch([() => props.runId, () => props.embedding, () => props.space, kind, requestedFeature], () => {search.value = ''; void load()}, {immediate:true})
function chooseFeature(value: string, selectedKind = kind.value) {
  void router.replace({path:route.path,query:{...route.query,feature_kind:selectedKind,feature_id:value || undefined}})
}
function changeKind(event: Event) { chooseFeature('', (event.target as HTMLSelectElement).value as 'gene'|'task') }
function difference(source: PointSource): number | null {
  const mean = data.value?.distributions[source]?.mean, control = data.value?.distributions.control?.mean
  return mean != null && control != null ? mean-control : null
}
async function exportFigure(format: 'svg'|'pdf'|'png'|'json') {
  if (!data.value || exporting.value) return
  const snapshot = data.value, current = exportController = new AbortController()
  const embedding = snapshot.method === 'joint-umap' ? 'umap' : 'pca'
  exporting.value = true; exportError.value = ''
  try {
    const token = await featureFilenameToken(snapshot.feature.id)
    const result = format === 'json' ? {blob:new Blob([JSON.stringify(snapshot,null,2)],{type:'application/json'}),filename:`${snapshot.run_id}_cell_state_${snapshot.embedding_space ?? 'expression'}_${embedding}_${snapshot.feature.kind}_${token}.json`}
      : await api.getCellStateFigure(snapshot.run_id,snapshot.feature.kind,snapshot.feature.id,format,current.signal,embedding,snapshot.embedding_space ?? 'expression')
    if (!current.signal.aborted && snapshot === data.value) downloadBlob(result.blob,result.filename)
  } catch (cause) { if (!current.signal.aborted) exportError.value = cause instanceof Error ? cause.message : '导出失败' }
  finally { if (!current.signal.aborted) exporting.value = false }
}
onBeforeUnmount(() => {controller?.abort(); exportController?.abort(); clearFigure()})
</script>
<template>
  <section class="scientific-cell-state" aria-label="单细胞科研图">
    <header v-if="!isMetabolic" class="state-heading"><div><span class="eyebrow">SINGLE-CELL / EXPRESSION DISTRIBUTION</span><h2>扰动前后细胞表达状态的分布变化</h2><p>比较对照、预测与可用实测的表达状态分布。每个点代表一个细胞的特征投影，不表示细胞形态、细胞器结构或物理位置。</p></div><span class="pill pill-neutral">{{ runSourceLabel(record?.request.mode,runId,record?.result_kind) }}</span></header>
    <div v-if="!featureKind" class="state-feature-controls">
      <label>指标类型<select aria-label="指标类型" :value="kind" @change="changeKind"><option value="gene">基因表达</option><option value="task">代谢任务分数</option></select></label>
      <label v-if="data">搜索指标<input v-model="search" aria-label="搜索逐细胞指标" placeholder="基因名或任务名称" /></label>
      <label v-if="data" class="feature-picker">选择指标<select aria-label="选择逐细胞指标" :value="data.feature.id" @change="chooseFeature(($event.target as HTMLSelectElement).value)"><option v-for="id in filtered" :key="id" :value="id">{{ kind === 'task' ? taskName(id) : id }}</option></select></label>
    </div>
    <p v-if="loading" role="status" class="state-message">正在读取本次{{ spaceLabel }} {{ isUmap ? 'UMAP' : 'PCA' }} 科研图…</p>
    <div v-else-if="error" role="alert" class="state-message"><h3>本次科研图暂不可用</h3><p>{{ error }}</p><button class="btn btn-sm" @click="load">重新加载</button><button v-if="requestedFeature && !featureKind" class="btn btn-sm" @click="chooseFeature('')">选择可用指标</button></div>
    <template v-else-if="data && figureUrl">
      <div class="figure-insight"><div><strong>先看指标变化，再结合分布读图</strong><p>{{ data.feature.kind === 'task' ? taskName(data.feature.id) : data.feature.id }}：对照均值 {{ fmtNumber(data.distributions.control?.mean) }} → 预测均值 {{ fmtNumber(data.distributions.predicted?.mean) }}，差值 {{ fmtDelta(difference('predicted')) }}（{{ data.feature.units }}）。这是群体描述性差值。</p></div><button type="button" class="btn btn-sm" @click="openAssistant(true)">解读此图</button></div>
      <div class="figure-toolbar"><div class="state-source-legend"><span v-for="source in sources" :key="source"><i :style="{background:sourceColors[source]}" />{{ sourceLabels[source] }} · n={{ data.distributions[source]?.n }}</span></div><div class="btn-row"><button class="btn btn-sm" @click="zoom=!zoom">{{ zoom?'适应页面':'放大科研图' }}</button><button v-for="format in (['svg','pdf','png','json'] as const)" :key="format" class="btn btn-sm" :disabled="exporting" @click="exportFigure(format)">导出 {{ format.toUpperCase() }}</button></div></div>
      <p v-if="exportError" role="alert" class="notice notice-warn">{{ exportError }}</p>
      <figure class="scientific-figure" :class="{zoom}"><img :src="figureUrl" :alt="`A ${spaceLabel}空间群体 ${isUmap ? 'UMAP' : 'PCA'} 叠加图，B 各群体选定指标着色图，C 逐细胞指标累积分布图`" /><figcaption>{{ isUmap ? '共同 UMAP' : '共同对照参考 PCA' }} · {{ isMetabolic ? `${data.embedding_preprocessing?.feature_count} 个代谢任务` : `${data.gene_count} 个基因` }}<template v-if="isUmap"> · 邻居数 {{ data.embedding_parameters?.n_neighbors }} · min_dist {{ data.embedding_parameters?.min_dist }}</template><template v-else> · 前两轴解释对照方差 {{ ((data.explained_variance_ratio[0]!+data.explained_variance_ratio[1]!)*100).toFixed(1) }}%</template> · 展示 {{ data.displayed_cells }} / {{ data.total_cells }} 个细胞</figcaption></figure>
      <div class="state-numbers"><h3>{{ data.feature.kind === 'task' ? taskName(data.feature.id) : data.feature.id }} <small>{{ data.feature.units }}</small></h3><p>查看各群体的有效细胞数、表达或任务分数分布。</p><div class="table-scroll"><table><thead><tr><th>群体</th><th>有效 / 总细胞</th><th>均值</th><th>中位数</th><th>四分位区间</th><th>均值 − 对照</th></tr></thead><tbody><tr v-for="source in sources" :key="source"><td>{{ sourceLabels[source] }}</td><td>{{ data.distributions[source]?.n_valid }} / {{ data.distributions[source]?.n }}</td><td>{{ fmtNumber(data.distributions[source]?.mean) }}</td><td>{{ fmtNumber(data.distributions[source]?.median) }}</td><td>{{ fmtNumber(data.distributions[source]?.q25) }} ～ {{ fmtNumber(data.distributions[source]?.q75) }}</td><td>{{ fmtDelta(difference(source)) }}</td></tr></tbody></table></div></div>
      <details class="figure-guide"><summary>科研图阅读指南 · A 分布 / B 着色 / C 累积分布</summary><div class="figure-reading" aria-label="科研图阅读说明">
        <div><b>A</b><strong>{{ isMetabolic ? '代谢状态分布有何差异？' : '表达状态分布有何差异？' }}</strong><p>颜色和点形区分对照、预测与可用实测；各群体共用 {{ isUmap ? 'UMAP' : 'PCA' }} 特征坐标，比较重叠、分散与分布差异。</p></div>
        <div><b>B</b><strong>哪些细胞的指标更高？</strong><p>同坐标、同色标：蓝色低、黄色高。颜色显示所选指标的数值。</p></div>
        <div><b>C</b><strong>所选指标的分布如何变化？</strong><p>横轴为指标数值，纵轴为不超过该值的细胞比例；曲线向右通常表示数值更高。</p></div>
      </div></details>
      <details class="state-boundary"><summary>状态分布图的含义与导出</summary><p>坐标表示{{ spaceLabel }}特征的相似关系，颜色表示所选基因表达或代谢任务分数。切换指标仅更新着色与分布统计，不重新拟合坐标。</p><p>点云形状不是细胞外形，点间距离不是物理距离。各群体不逐细胞配对；分布差异不表示单个细胞的迁移轨迹，也不能单凭点群分离判断预测准确性。代谢任务分数不等于实测代谢通量。</p><p>支持导出 PDF、SVG、PNG 和数据文件。</p></details>
    </template>
  </section>
</template>
<style scoped>
.figure-insight{display:flex;align-items:center;justify-content:space-between;gap:22px;border-left:3px solid var(--primary);background:var(--surface-soft);padding:16px 18px;margin:18px 0}.figure-insight strong{font-size:13px;font-weight:500}.figure-insight p{font-size:12px;color:var(--muted);line-height:1.9;margin:7px 0 0}.figure-insight>.btn{flex:none}
.scientific-figure:not(.zoom) img{min-width:0}
.state-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:20px}.state-heading h2{font-size:24px;font-weight:500;margin:10px 0}.state-heading p{color:var(--muted);font-size:12px;line-height:1.8}.figure-reading{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;border-top:1px solid var(--border);border-bottom:1px solid var(--border);padding:20px 0}.figure-reading b{font:700 18px Arial,sans-serif;color:var(--primary);display:inline-block;margin-right:10px}.figure-reading strong{font-size:12px;font-weight:500}.figure-reading p{font-size:11px;line-height:1.8;color:var(--muted);margin:8px 0 0}.state-feature-controls{display:flex;gap:14px;align-items:end;flex-wrap:wrap;margin:24px 0}.state-feature-controls label{font-size:11px;color:var(--muted);min-width:140px}.state-feature-controls select,.state-feature-controls input{display:block;margin-top:7px;width:100%;padding:10px;border:1px solid var(--border);background:var(--field-bg);color:var(--ink);font:12px var(--font);max-width:100%}.feature-picker{flex:1;min-width:260px!important}.figure-toolbar{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}.state-source-legend{display:flex;flex-wrap:wrap;gap:16px;font-size:11px}.state-source-legend i{display:inline-block;width:8px;height:8px;margin-right:6px;border-radius:50%}.state-evidence-note{font-size:11px;color:var(--muted);margin-top:18px}.scientific-figure{margin:18px 0;background:var(--figure-bg);border:1px solid var(--border);overflow-x:auto}.scientific-figure img{display:block;width:100%;min-width:850px;height:auto}.scientific-figure.zoom img{width:2100px;max-width:none}.scientific-figure figcaption{font-size:11px;line-height:1.8;padding:12px 18px;border-top:1px solid var(--border);color:var(--muted)}.state-numbers h3{font-size:15px;font-weight:500;overflow-wrap:anywhere}.state-numbers small{font-size:11px;color:var(--muted);margin-left:12px}.state-numbers p,.state-boundary{font-size:11px;color:var(--muted);line-height:1.9}.state-numbers table{width:100%;font-size:12px;border-collapse:collapse;white-space:nowrap}.state-numbers td,.state-numbers th{padding:12px;text-align:right;border-bottom:1px solid var(--border);font-weight:400}.state-numbers td:first-child,.state-numbers th:first-child{text-align:left}.state-numbers thead{background:var(--table-head-bg)}.state-boundary{border-top:1px solid var(--border);margin-top:24px;padding-top:12px}.state-boundary details{margin-top:16px}.state-boundary summary{cursor:pointer;color:var(--primary)}.state-boundary .mono{overflow-wrap:anywhere}.state-message{padding:60px 20px;text-align:center;background:var(--message-bg);font-size:12px;line-height:1.9}.state-message h3{font-size:16px;font-weight:500}.state-message button{margin:12px 4px}.table-scroll{overflow:auto}
</style>
