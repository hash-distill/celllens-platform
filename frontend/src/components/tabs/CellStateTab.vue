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
const filtered = computed(() => options.value.filter(id => id === data.value?.feature.id || id.toLowerCase().includes(search.value.toLowerCase().trim())))
const sourceLabels: Record<PointSource,string> = {control:'扰动前 / 对照',predicted:'扰动后 / 模型预测',observed:'扰动后 / 实测'}
const sourceColors: Record<PointSource,string> = {control:'#0072B2',predicted:'#D55E00',observed:'#009E73'}
const sources = computed(() => (['control','predicted','observed'] as PointSource[]).filter(source => data.value?.distributions[source]))
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
    if (!current.signal.aborted) figureUrl.value = URL.createObjectURL(figure)
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
    const blob = format === 'json' ? new Blob([JSON.stringify(snapshot,null,2)],{type:'application/json'})
      : await api.getCellStateFigure(props.runId,snapshot.feature.kind,snapshot.feature.id,format,current.signal,embedding,snapshot.embedding_space ?? 'expression')
    if (!current.signal.aborted) downloadBlob(blob,`${snapshot.run_id}_cell_state_${snapshot.embedding_space ?? 'expression'}_${embedding}_${snapshot.feature.kind}.${format}`)
  } catch (cause) { if (!current.signal.aborted) exportError.value = cause instanceof Error ? cause.message : '导出失败' }
  finally { if (!current.signal.aborted) exporting.value = false }
}
onBeforeUnmount(() => {controller?.abort(); exportController?.abort(); clearFigure()})
</script>
<template>
  <section class="scientific-cell-state" aria-label="单细胞科研图">
    <header v-if="!isMetabolic" class="state-heading"><div><span class="eyebrow">SINGLE-CELL / MODEL PREDICTION</span><h2>模型预测的细胞群体变化</h2><p>先看整体表达分布，再看有完整预测变化数值的基因或代谢任务。</p></div><span class="pill pill-neutral">{{ runSourceLabel(record?.request.mode,runId,record?.result_kind) }}</span></header>
    <div class="figure-reading" aria-label="科研图阅读说明">
      <div><b>A</b><strong>{{ isUmap ? `局部${isMetabolic ? '代谢' : '表达'}结构是否不同？` : '整体分布有没有改变？' }}</strong><p>颜色和点形区分群体；{{ isUmap ? `共同 UMAP 坐标用于探索相似${spaceLabel}状态的邻近关系。` : '共同 PCA 坐标用于观察重叠、分散与偏移。' }}</p></div>
      <div><b>B</b><strong>哪些细胞的指标更高？</strong><p>同坐标、同色标：蓝色低、黄色高。颜色对应选定指标，不代表群体。</p></div>
      <div><b>C</b><strong>变化发生在整个群体吗？</strong><p>横轴为指标数值，纵轴为不超过该值的细胞比例；曲线向右通常表示数值更高。</p></div>
    </div>
    <div v-if="!featureKind" class="state-feature-controls">
      <label>指标类型<select aria-label="指标类型" :value="kind" @change="changeKind"><option value="gene">基因表达</option><option value="task">代谢任务分数</option></select></label>
      <label v-if="data">搜索指标<input v-model="search" aria-label="搜索逐细胞指标" placeholder="基因名或任务名称" /></label>
      <label v-if="data" class="feature-picker">选择指标<select aria-label="选择逐细胞指标" :value="data.feature.id" @change="chooseFeature(($event.target as HTMLSelectElement).value)"><option v-for="id in filtered" :key="id" :value="id">{{ id }}</option></select></label>
    </div>
    <p v-if="loading" role="status" class="state-message">正在读取本次{{ spaceLabel }} {{ isUmap ? 'UMAP' : 'PCA' }} 科研图…</p>
    <div v-else-if="error" role="alert" class="state-message"><h3>本次科研图暂不可用</h3><p>{{ error }}</p><button class="btn btn-sm" @click="load">重新加载</button><button v-if="requestedFeature && !featureKind" class="btn btn-sm" @click="chooseFeature('')">选择可用指标</button></div>
    <template v-else-if="data && figureUrl">
      <div class="figure-toolbar"><div class="state-source-legend"><span v-for="source in sources" :key="source"><i :style="{background:sourceColors[source]}" />{{ sourceLabels[source] }} · n={{ data.distributions[source]?.n }}</span></div><div class="btn-row"><button class="btn btn-sm" @click="zoom=!zoom">{{ zoom?'适应页面':'放大科研图' }}</button><button v-for="format in (['svg','pdf','png','json'] as const)" :key="format" class="btn btn-sm" :disabled="exporting" @click="exportFigure(format)">导出 {{ format.toUpperCase() }}</button></div></div>
      <p v-if="exportError" role="alert" class="notice notice-warn">{{ exportError }}</p>
      <figure class="scientific-figure" :class="{zoom}"><img :src="figureUrl" :alt="`A ${spaceLabel}空间群体 ${isUmap ? 'UMAP' : 'PCA'} 叠加图，B 各群体选定指标着色图，C 逐细胞指标累积分布图`" /><figcaption>{{ isUmap ? '共同 UMAP' : '共同对照参考 PCA' }} · {{ isMetabolic ? `${data.embedding_preprocessing?.feature_count} 个代谢任务` : `${data.gene_count} 个基因` }}<template v-if="isUmap"> · 邻居数 {{ data.embedding_parameters?.n_neighbors }} · min_dist {{ data.embedding_parameters?.min_dist }}</template><template v-else> · 前两轴解释对照方差 {{ ((data.explained_variance_ratio[0]!+data.explained_variance_ratio[1]!)*100).toFixed(1) }}%</template> · 展示 {{ data.displayed_cells }} / {{ data.total_cells }} 个细胞</figcaption></figure>
      <div class="state-numbers"><h3>{{ data.feature.id }} <small>{{ data.feature.units }}</small></h3><p>分布与下表使用全部有效细胞。n 是细胞数；缺失值不作零值处理。均值差不代表统计显著性。</p><div class="table-scroll"><table><thead><tr><th>群体</th><th>有效 / 总细胞</th><th>均值</th><th>中位数</th><th>四分位区间</th><th>均值 − 对照</th></tr></thead><tbody><tr v-for="source in sources" :key="source"><td>{{ sourceLabels[source] }}</td><td>{{ data.distributions[source]?.n_valid }} / {{ data.distributions[source]?.n }}</td><td>{{ fmtNumber(data.distributions[source]?.mean) }}</td><td>{{ fmtNumber(data.distributions[source]?.median) }}</td><td>{{ fmtNumber(data.distributions[source]?.q25) }} ～ {{ fmtNumber(data.distributions[source]?.q75) }}</td><td>{{ fmtDelta(difference(source)) }}</td></tr></tbody></table></div></div>
      <div class="state-boundary"><p v-if="isMetabolic">坐标由本次保存的逐细胞代谢任务分数计算，使用所有群体数值完整、且对照中存在变化的任务；按对照均值与标准差统一标准化，缺失任务不补零。颜色和分布仍显示所选任务的原始分数。</p><p v-if="isUmap">本次各群体的{{ spaceLabel }}数据先共同降至 {{ data.embedding_parameters?.preprocessing.n_components }} 个主成分，再联合拟合 UMAP，随机种子固定为 {{ data.embedding_parameters?.random_state }}。切换指标仅改变着色；图上群体间距和密度不量化扰动效应，不同实验独立生成的坐标不能直接比较。</p><p v-else>PCA 在{{ isMetabolic ? '标准化后的对照任务分数' : '完整对照的 log1p(CP10K) 表达' }}上拟合{{ isMetabolic ? '' : '，仅中心化' }}；预测和实测使用同一中心与基底。</p><p>图形中的位置是{{ spaceLabel }}空间坐标，细胞不逐点配对。代谢任务分数来自本次保存的逐细胞 scCellFie 结果，不等于代谢通量。</p><p>此图用于发现值得继续研究的分布差异。预测准确性请结合<RouterLink :to="{path:'/demo',query:{run:runId,tab:'validation'}}">预测验证</RouterLink>；细胞数量不能替代生物学重复。PDF / SVG 为矢量图，PNG 为 300 dpi。</p><details><summary>数据来源与核对记录</summary><p>原始运行：{{ data.provenance.source_run_id }}；已核对已有基因均值与逐细胞任务 ID。</p><p v-if="isMetabolic">参与降维的任务：{{ data.embedding_preprocessing?.feature_ids.join('、') }}</p><p class="mono">Manifest SHA256: {{ data.provenance.manifest_sha256 }}</p></details></div>
    </template>
  </section>
</template>
<style scoped>
.state-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:20px}.state-heading h2{font-size:24px;font-weight:500;margin:10px 0}.state-heading p{color:var(--muted);font-size:12px;line-height:1.8}.figure-reading{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;border-top:1px solid var(--border);border-bottom:1px solid var(--border);padding:20px 0}.figure-reading b{font:700 18px Arial,sans-serif;color:var(--primary);display:inline-block;margin-right:10px}.figure-reading strong{font-size:12px;font-weight:500}.figure-reading p{font-size:11px;line-height:1.8;color:var(--muted);margin:8px 0 0}.state-feature-controls{display:flex;gap:14px;align-items:end;flex-wrap:wrap;margin:24px 0}.state-feature-controls label{font-size:11px;color:var(--muted);min-width:140px}.state-feature-controls select,.state-feature-controls input{display:block;margin-top:7px;width:100%;padding:10px;border:1px solid var(--border);background:var(--field-bg);color:var(--ink);font:12px var(--font);max-width:100%}.feature-picker{flex:1;min-width:260px!important}.figure-toolbar{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}.state-source-legend{display:flex;flex-wrap:wrap;gap:16px;font-size:11px}.state-source-legend i{display:inline-block;width:8px;height:8px;margin-right:6px;border-radius:50%}.state-evidence-note{font-size:11px;color:var(--muted);margin-top:18px}.scientific-figure{margin:18px 0;background:var(--figure-bg);border:1px solid var(--border);overflow-x:auto}.scientific-figure img{display:block;width:100%;min-width:850px;height:auto}.scientific-figure.zoom img{width:2100px;max-width:none}.scientific-figure figcaption{font-size:11px;line-height:1.8;padding:12px 18px;border-top:1px solid var(--border);color:var(--muted)}.state-numbers h3{font-size:15px;font-weight:500;overflow-wrap:anywhere}.state-numbers small{font-size:11px;color:var(--muted);margin-left:12px}.state-numbers p,.state-boundary{font-size:11px;color:var(--muted);line-height:1.9}.state-numbers table{width:100%;font-size:12px;border-collapse:collapse;white-space:nowrap}.state-numbers td,.state-numbers th{padding:12px;text-align:right;border-bottom:1px solid var(--border);font-weight:400}.state-numbers td:first-child,.state-numbers th:first-child{text-align:left}.state-numbers thead{background:var(--table-head-bg)}.state-boundary{border-top:1px solid var(--border);margin-top:24px;padding-top:12px}.state-boundary details{margin-top:16px}.state-boundary summary{cursor:pointer;color:var(--primary)}.state-boundary .mono{overflow-wrap:anywhere}.state-message{padding:60px 20px;text-align:center;background:var(--message-bg);font-size:12px;line-height:1.9}.state-message h3{font-size:16px;font-weight:500}.state-message button{margin:12px 4px}.table-scroll{overflow:auto}
</style>
