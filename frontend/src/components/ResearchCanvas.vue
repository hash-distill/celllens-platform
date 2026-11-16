<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { EChartsOption } from 'echarts'
import CellScene from './CellScene.vue'
import type { CellRegionKey } from '../lib/cellScene'
import { apiFetch } from '../api/http'
import { useEChart, CHART_COLORS } from '../charts/useEChart'
import type { ResearchKind, ResearchSelection } from '../types/research'
import { escapeTooltip, projectionBounds, structureTasks } from '../utils/researchCanvas'
import type { ProjectionPoint, ProjectionSource as Source, StructureTask } from '../utils/researchCanvas'
const props = withDefaults(defineProps<{ kind: ResearchKind; recordId: string; tasks?: StructureTask[]; knowledgeVersion?: string; readOnly?: boolean }>(), { tasks: () => [], readOnly: false })
const emit = defineEmits<{ selection: [value: ResearchSelection]; 'select-task': [id: string] }>()
interface Projection {
 method: string; data_kind?: string; points: ProjectionPoint[]; counts?: Partial<Record<Source, number | null>>
 gene_count?: number; input_units?: string; provenance?: Record<string, unknown>; explained_variance_ratio?: number[]
 fit_source?: unknown; parameters?: unknown; preprocessing?: unknown
}
const selected = ref<CellRegionKey | null>(null), data = ref<Projection | null>(null), error = ref(''), loading = ref(false), retry = ref(0)
const group = ref<Source | 'all'>('all'), plot = ref<HTMLElement | null>(null), embedding = ref<'pca' | 'umap'>('pca')
const names: Record<Source, string> = { control: '实测对照', predicted: '模型预测', observed: '扰动实测' }
const structures: Record<CellRegionKey, { name: string; description: string }> = {
 nucleus: { name: '细胞核', description: '遗传信息储存与转录调控的结构示意。当前实验没有细胞核形态或定位测量。' },
 mitochondria: { name: '线粒体', description: 'RNA 派生功能分数不等于呼吸速率、通量或膜电位；能量代谢分类不用于推定线粒体定位。' },
 er: { name: '内质网', description: '仅关联冻结知识库中 Processing in the ER 分类；表达变化不推断结构形态。' },
 golgi: { name: '高尔基体', description: '仅关联冻结知识库中 Processing in the Golgi 分类；本次数据没有测量其形态。' },
 membrane: { name: '细胞膜', description: '细胞边界的结构示意。转录组投影不提供膜表面结构或运动轨迹。' },
 cytoplasm: { name: '细胞质', description: '细胞内环境的结构示意。图中位置没有与单细胞表达坐标一一对应。' },
}
const selectedInfo = computed(() => selected.value ? structures[selected.value] : null)
const relatedTasks = computed(() => structureTasks(props.tasks, selected.value))
const sources = computed(() => (['control', 'predicted', 'observed'] as Source[]).filter(source => data.value?.points.some(point => point.source === source)))
const visiblePoints = computed(() => (data.value?.points ?? []).filter(point => group.value === 'all' || point.source === group.value))
const bounds = computed(() => projectionBounds(data.value?.points ?? []))
const axis = computed(() => embedding.value === 'umap' ? 'UMAP' : 'PC')
const selectedTotal = computed(() => {
 const values = (group.value === 'all' ? sources.value : [group.value]).map(source => data.value?.counts?.[source])
 return values.length && values.every(value => typeof value === 'number' && Number.isFinite(value)) ? values.reduce<number>((sum, value) => sum + value!, 0) : null
})
const selectionLayer = ref<ResearchSelection['layer']>('expression')
const detail = (value: unknown) => value == null ? '未记录' : typeof value === 'string' ? value : JSON.stringify(value)
function selectProjection() { selectionLayer.value = 'expression'; emit('selection', { layer: 'expression', projection_id: embedding.value, group_id: group.value === 'all' ? undefined : group.value }) }
function selectStructure(key: CellRegionKey) { selectionLayer.value = 'structure'; selected.value = key; emit('selection', { layer: 'structure' }) }
watch([() => props.kind, () => props.recordId], () => { selected.value = null; group.value = 'all'; embedding.value = 'pca' })
watch([group, embedding], selectProjection)
watch([() => props.kind, () => props.recordId, embedding, retry], async (_v, _o, cleanup) => {
 const control = new AbortController(); cleanup(() => control.abort()); data.value = null; error.value = ''; loading.value = true
 try {
  const response = await apiFetch<Projection>('/research/results/' + props.kind + '/' + encodeURIComponent(props.recordId) + '/projection', { query: { embedding: embedding.value }, signal: control.signal })
  if (control.signal.aborted) return
  if (!response.method || /random|synthetic|demo/i.test(response.method) || response.data_kind === 'synthetic_demo') throw new Error('该历史坐标没有可核验的真实表达投影，暂不展示。')
  data.value = { ...response, points: response.points.filter(point => Number.isFinite(point.x) && Number.isFinite(point.y) && ['control', 'observed', 'predicted'].includes(point.source)) }
  if (group.value !== 'all' && !sources.value.includes(group.value)) group.value = 'all'
  if (selectionLayer.value === 'expression') selectProjection()
 } catch (e) { if (!control.signal.aborted) error.value = e instanceof Error ? e.message : '表达投影暂不可用' }
 finally { if (!control.signal.aborted) loading.value = false }
}, { immediate: true })
function option(): EChartsOption { return {
 animation: false, grid: { top: 25, right: 22, bottom: 40, left: 52 },
 tooltip: { trigger: 'item', confine: true, formatter: (params: unknown) => {
  const item = params as { data: { point: ProjectionPoint } }, point = item.data.point
  return names[point.source] + '<br/>cell_id: ' + escapeTooltip(point.cell_id ?? point.cell_index) + '<br/>source: ' + point.source + '<br/>' + axis.value + ' 1: ' + point.x.toFixed(3) + '<br/>' + axis.value + ' 2: ' + point.y.toFixed(3)
 } },
 xAxis: { type: 'value', name: axis.value + ' 1', nameLocation: 'middle', nameGap: 26, min: bounds.value.x[0], max: bounds.value.x[1], axisLabel: { fontSize: 11, color: '#64748b', formatter: (value: number) => Number(value.toPrecision(3)).toLocaleString('zh-CN') }, splitLine: { lineStyle: { color: '#e5e8e0' } } },
 yAxis: { type: 'value', name: axis.value + ' 2', min: bounds.value.y[0], max: bounds.value.y[1], axisLabel: { fontSize: 11, color: '#64748b', formatter: (value: number) => Number(value.toPrecision(3)).toLocaleString('zh-CN') }, splitLine: { lineStyle: { color: '#e5e8e0' } } },
 dataZoom: [{ type: 'inside', xAxisIndex: 0, filterMode: 'none', zoomOnMouseWheel: 'ctrl', moveOnMouseWheel: false }, { type: 'inside', yAxisIndex: 0, filterMode: 'none', zoomOnMouseWheel: 'ctrl', moveOnMouseWheel: false }],
 series: sources.value.filter(source => group.value === 'all' || group.value === source).map(source => ({ type: 'scatter', name: names[source], symbolSize: 5, itemStyle: { color: CHART_COLORS[source], opacity: .75 }, data: (data.value?.points ?? []).filter(point => point.source === source).map(point => ({ value: [point.x, point.y], point })) })),
} }
const { getChart } = useEChart(plot, option, [data, group])
function resetProjection() { getChart()?.dispatchAction({ type: 'dataZoom', batch: [{ dataZoomIndex: 0, start: 0, end: 100 }, { dataZoomIndex: 1, start: 0, end: 100 }] }) }
function zoomProjection(factor: number) {
 const chart = getChart(); if (!chart) return
 const current = chart.getOption().dataZoom as Array<{ start?: number; end?: number }> | undefined
 chart.dispatchAction({ type: 'dataZoom', batch: [0, 1].map(index => {
  const start = current?.[index]?.start ?? 0, end = current?.[index]?.end ?? 100, middle = (start + end) / 2
  const span = Math.max(2, Math.min(100, (end - start) * factor)), left = Math.max(0, Math.min(100 - span, middle - span / 2))
  return { dataZoomIndex: index, start: left, end: left + span }
 }) })
}
</script>
<template>
 <section class="research-canvas" aria-label="表达空间与结构分类导航">
  <div class="expression-panel"><header><div><span class="canvas-kicker">EXPRESSION LANDSCAPE</span><h2>{{ kind === 'prediction' ? '原运行群体的表达分布' : '实测群体的表达分布' }}</h2></div><div class="embedding-switch"><button v-for="item in (['pca','umap'] as const)" :key="item" :aria-pressed="embedding===item" @click="embedding=item">{{item.toUpperCase()}}</button></div></header>
  <p v-if="kind==='prediction'" class="projection-scope">投影使用原运行的实测对照与模型预测；与匹配实测诊断的筛选群体分别展示。</p>
   <div class="group-switch" aria-label="投影群体"><button :aria-pressed="group==='all'" @click="group='all';selectProjection()">全部群体</button><button v-for="source in sources" :key="source" :aria-pressed="group===source" @click="group=source;selectProjection()"><i :style="{background:CHART_COLORS[source]}"/>{{names[source]}}</button></div>
   <div class="projection-frame"><div ref="plot" class="projection-plot" role="img" aria-label="来自冻结结果的表达投影；群体筛选使用固定的全体坐标轴域"/><div v-if="loading||error||!data?.points.length" class="projection-message" role="status"><strong>{{loading?'正在读取表达坐标':error?'本次投影不可用':'尚无表达坐标'}}</strong><p v-if="error">{{error}}</p><button v-if="error" class="btn btn-sm" @click="retry++">重新读取</button></div></div>
   <div class="projection-tools"><button @click="zoomProjection(.7)" :disabled="!data">放大</button><button @click="zoomProjection(1.4)" :disabled="!data">缩小</button><button @click="resetProjection" :disabled="!data">恢复完整范围</button><span>Ctrl + 滚轮缩放 · 拖动平移</span></div>
   <footer><strong v-if="data">所选群体 {{visiblePoints.length.toLocaleString('zh-CN')}} / 已保存 {{data.points.length.toLocaleString('zh-CN')}} 条坐标 · 所选群体总细胞 {{selectedTotal ?? '未记录'}}</strong><p>所有群体使用相同轴域，筛选不重新拟合；缩放只改变视窗。点表示表达记录，不代表细胞运动或显著性。</p>
    <details v-if="data" class="projection-method"><summary>投影方法与来源 · {{embedding.toUpperCase()}}</summary><dl><dt>冻结方法</dt><dd>{{data.method}}</dd><dt>特征与尺度</dt><dd>{{data.gene_count ?? '未记录'}} 个基因 · {{data.input_units || '未记录'}}</dd><dt>拟合范围</dt><dd>{{detail(data.fit_source)}} · 图中群体：{{sources.map(source=>names[source]).join('、')}}</dd><dt>{{embedding==='pca'?'解释方差比例':'UMAP 参数'}}</dt><dd>{{detail(embedding==='pca'?data.explained_variance_ratio:data.parameters)}}</dd><dt>预处理</dt><dd>{{detail(data.preprocessing)}}</dd><dt>坐标来源</dt><dd>{{detail(data.provenance)}}</dd></dl><p>未记录项不在读取时重算；投影群体与上方摘要的匹配群体可能不同，以本图冻结计数为准。</p></details>
   </footer>
  </div>
  <div class="structure-panel"><header><div><span class="canvas-kicker">STRUCTURE REFERENCE</span><h2>结构与功能分类导航</h2></div><span class="scene-label">结构示意</span></header><CellScene :selected="selected" compact @select="selectStructure"/><div class="structure-caption"><strong>{{selectedInfo?.name||'选择结构，核对收录的功能任务'}}</strong><p>{{selectedInfo?.description||'可旋转、缩放或点选结构。模型为示意，不代表本次测得的形态。'}}</p>
   <template v-if="selected"><div v-if="relatedTasks.length" class="structure-task-list"><span>{{relatedTasks.length}} 项本次有评分的任务 · {{knowledgeVersion || '知识库版本见任务证据'}}</span><button v-for="task in relatedTasks" :key="task.id" :disabled="readOnly" :title="readOnly ? '成员证据在私人工作区中查看' : '查看本次任务证据'" @click="emit('select-task',task.id)"><strong>{{task.label || task.id}}</strong><small>{{task.rawCategory}} · 关联基因覆盖 {{task.coverage == null ? '未知' : Math.round(task.coverage*100)+'%'}} {{readOnly ? '· 私人工作区查看成员' : '→'}}</small></button></div><p v-else>{{selected==='er'||selected==='golgi'?'当前记录没有此显式分类下可用的任务评分。':'此结构暂无显式收录的功能分类。'}}</p><p class="classification-note">关联来自知识库任务分类，不是本次定位或细胞器活性测量。</p></template>
  </div></div>
 </section>
</template>
<style scoped>
.research-canvas{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,.85fr);gap:16px;margin:0 20px 20px;align-items:start}.structure-panel,.expression-panel{min-width:0;border:1px solid var(--border);border-radius:14px;overflow:hidden;background:var(--card)}.structure-panel{background:radial-gradient(ellipse at 48% 40%,#315d3e,#183f2d 75%);color:#e2ebd5}header{padding:17px 18px 8px;display:flex;gap:10px;justify-content:space-between;align-items:start}.canvas-kicker{font:10px Consolas,monospace;letter-spacing:1.3px;color:var(--muted)}h2{font-size:16px;font-weight:500;margin:7px 0}.structure-panel .canvas-kicker{color:#afc6a4}.scene-label{font-size:11px;border:1px solid #769565;border-radius:20px;padding:5px 8px;white-space:nowrap}.structure-panel :deep(.cl-cell-scene){height:280px;min-height:280px}.structure-caption{margin:0 18px 18px;border-top:1px solid #4b6c4c;padding-top:12px}.structure-caption strong{font-size:13px;font-weight:500}.structure-caption p{font-size:12px;line-height:1.8;color:#c0d2b3;margin:7px 0 0}.structure-task-list{margin-top:12px;display:grid;gap:7px;max-height:210px;overflow:auto}.structure-task-list>span{font-size:12px;color:#ceddbf}.structure-task-list button{text-align:left;border:1px solid #79916c;border-radius:6px;background:#173a2b;color:#edf1dc;padding:9px;cursor:pointer}.structure-task-list small{display:block;font-size:11px;color:#cadaba;margin-top:5px}.classification-note{border-top:1px solid #4b6c4c;padding-top:8px}.embedding-switch{display:flex;gap:3px;background:var(--surface-soft);border-radius:7px;padding:3px}.embedding-switch button{padding:5px 8px;font:12px Consolas,monospace;border:0;border-radius:5px;background:transparent;color:var(--muted);cursor:pointer}.embedding-switch button[aria-pressed=true]{background:var(--primary);color:#f3f7e9}.group-switch{display:flex;gap:5px;padding:0 16px;flex-wrap:wrap}.group-switch button,.projection-tools button{background:transparent;border:1px solid var(--border);border-radius:6px;padding:5px 8px;font:12px var(--font);color:var(--muted);cursor:pointer}.group-switch button[aria-pressed=true]{background:var(--primary-weak);border-color:var(--primary);color:var(--primary)}.group-switch i{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px}.projection-frame{position:relative;margin:5px 8px 0}.projection-plot{width:100%;height:225px}.projection-message{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px;background:var(--card);font-size:13px;line-height:1.8;text-align:center}.projection-message p{color:var(--muted);max-width:330px}.projection-tools{display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:0 18px 12px}.projection-tools span{font-size:11px;color:var(--muted)}.expression-panel footer{margin:0 18px 16px;padding-top:12px;border-top:1px solid var(--border)}footer strong{font-size:12px;font-weight:500;color:var(--primary-strong)}footer p{font-size:12px;line-height:1.8;color:var(--muted);margin:7px 0}.projection-method{font-size:12px;line-height:1.8}.projection-method summary{cursor:pointer;color:var(--primary-strong)}.projection-method dl{display:grid;grid-template-columns:80px minmax(0,1fr);gap:7px;margin:10px 0}.projection-method dt{color:var(--muted)}.projection-method dd{margin:0;overflow-wrap:anywhere}button:focus-visible,summary:focus-visible{outline:2px solid var(--primary);outline-offset:3px}.structure-panel button:focus-visible{outline-color:#efd897}@media(max-width:1000px){.research-canvas{grid-template-columns:1fr}.structure-panel :deep(.cl-cell-scene){height:300px}.projection-plot{height:250px}}@media(max-width:500px){.research-canvas{margin:0 12px 16px;gap:12px}header{padding:14px 13px 7px;flex-wrap:wrap}.structure-panel :deep(.cl-cell-scene){height:330px;min-height:330px}.projection-method dl{grid-template-columns:1fr;gap:3px}.projection-method dd{margin-bottom:6px}}
</style>
