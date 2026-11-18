<script setup lang="ts">
import { computed, nextTick, ref, shallowRef, watch } from 'vue'
import type { OverviewRow, OverviewSource } from '../utils/resultOverview'
import { expressionPairs, strongestGenes, scatterSample } from '../utils/expressionResponse'
import { scoreLabel } from '../utils/metabolicVisualization'
import { measuredApi } from '../api/measured'
import { downloadBlob, downloadCsv } from '../utils/csv'
import SingleCellAtlas from './SingleCellAtlas.vue'
import GeneDistribution from './GeneDistribution.vue'
const props = defineProps<{ recordId: string; sourceKind: OverviewSource; rows?: OverviewRow[]; units?: string; selectedId?: string; readOnly?: boolean; truncated?: boolean }>()
const emit = defineEmits<{ select: [id: string] }>()
const measuredRows = shallowRef<OverviewRow[]>([]), loading = ref(false), error = ref(''), progress = ref(0), total = ref(0), retry = ref(0)
const selected = ref(''), query = ref(''), mode = ref<'bars'|'heatmap'>('bars'), direction = ref('all')
const genePicker = ref<HTMLElement | null>(null)
async function inspectAtlasGene(id: string) { choose(id); await nextTick(); genePicker.value?.scrollIntoView({behavior:'smooth',block:'start'}) }
const barPlot = ref<SVGSVGElement | null>(null), scatterPlot = ref<SVGSVGElement | null>(null)
watch([() => props.recordId, () => props.sourceKind, retry], async (_, _old, cleanup) => {
  const controller = new AbortController(); cleanup(() => controller.abort())
  measuredRows.value = []; loading.value = false; error.value = ''; progress.value = 0; total.value = 0; selected.value = ''; query.value = ''; direction.value = 'all'
  if (props.sourceKind !== 'measured') return
  loading.value = true
  try {
    const first = await measuredApi.expressionSummary(props.recordId, controller.signal)
    if(controller.signal.aborted) return
    if(first.record_id !== props.recordId) throw new Error('表达摘要来源与当前研究不一致')
    total.value = first.total
    const rows = first.items; progress.value = rows.length
    if(rows.length !== first.total || new Set(rows.map(row => row.gene)).size !== first.total) throw new Error('基因数据不完整，已停止绘图，请重试')
    measuredRows.value = rows.map(row => ({id: row.gene!, control: row.control, observed: row.observed, delta: row.observed_delta}))
  } catch(e) { if(!controller.signal.aborted) error.value = e instanceof Error ? e.message : '表达结果读取失败' }
  finally { if(!controller.signal.aborted) loading.value = false }
}, {immediate:true})
const rows = computed(() => props.rows ?? measuredRows.value)
const pairs = computed(() => expressionPairs(rows.value, props.sourceKind))
const complete = computed(() => pairs.value.filter(row => row.delta !== null))
const up = computed(() => complete.value.filter(row => row.delta! > 0).length)
const down = computed(() => complete.value.filter(row => row.delta! < 0).length)
const ranked = computed(() => strongestGenes(pairs.value.filter(row => direction.value === 'all' || (row.delta !== null && (direction.value === 'up' ? row.delta > 0 : row.delta < 0)))))
const points = computed(() => scatterSample(pairs.value))
const maxDelta = computed(() => Math.max(.000001, ...ranked.value.map(row => Math.abs(row.delta!))))
const domain = computed(() => {
  let lo = 0, hi = 0
  for(const row of complete.value) {lo = Math.min(lo, row.control!, row.target!); hi = Math.max(hi, row.control!, row.target!)}
  return {lo, hi: hi === lo ? lo + 1 : hi, span: hi === lo ? 1 : hi - lo}
})
const current = computed(() => pairs.value.find(row => row.id === selected.value))
const atlasGenes = computed(() => { const ids = strongestGenes(pairs.value).map(row => row.id); if(selected.value && !ids.includes(selected.value)) ids.push(selected.value); return ids })
const targetLabel = computed(() => props.sourceKind === 'run' ? '模型预测' : '扰动实测')
const options = computed(() => pairs.value.filter(row => row.id.toLowerCase().includes(query.value.trim().toLowerCase())).slice(0,20))
watch([pairs, () => props.selectedId], () => { selected.value = pairs.value.some(row => row.id === props.selectedId) ? props.selectedId! : pairs.value.some(row => row.id === selected.value) ? selected.value : strongestGenes(pairs.value,1)[0]?.id || '' }, {immediate:true})
function choose(id: string) { selected.value = id; query.value = id }
function chooseQuery() { const match = pairs.value.find(row => row.id.toLowerCase() === query.value.trim().toLowerCase()) || options.value[0]; if(match) choose(match.id) }
const color = (delta: number | null) => delta === null ? '#9da9a1' : delta > 0 ? '#ad7139' : delta < 0 ? '#25816c' : '#82938e'
const sx = (value: number) => 62 + (value - domain.value.lo) / domain.value.span * 430
const sy = (value: number) => 352 - (value - domain.value.lo) / domain.value.span * 300
function heat(value: number | null) {
  if(value === null) return '#e5e8e3'
  const ratio = (value - domain.value.lo) / domain.value.span
  return `rgb(${Math.round(240 - 205 * ratio)},${Math.round(246 - 134 * ratio)},${Math.round(232 - 145 * ratio)})`
}
function savePlot(kind: 'ranking' | 'scatter') {
  const node = kind === 'ranking' ? barPlot.value : scatterPlot.value
  if(!node) return
  const copy = node.cloneNode(true) as SVGSVGElement; copy.setAttribute('xmlns','http://www.w3.org/2000/svg')
  downloadBlob(new Blob([new XMLSerializer().serializeToString(copy)],{type:'image/svg+xml;charset=utf-8'}),`${props.recordId}_expression-${kind === 'ranking' ? mode.value : kind}.svg`)
}
function saveRows() {
  downloadCsv(`${props.recordId}_expression-chart-data.csv`,['研究记录','结果类型','基因','对照',targetLabel.value,'均值差','表达尺度'],pairs.value.map(row=>[props.recordId,props.sourceKind,row.id,row.control,row.target,row.delta,props.units]))
}
</script>
<template>
  <section class="expression-gallery" aria-label="表达响应可视化">
    <header class="gallery-heading"><div><span class="eyebrow">EXPRESSION RESPONSE</span><h2>从群体差异，定位基因响应</h2><p>比较表达变化方向、两组均值与单基因分布。</p></div><button class="btn btn-sm" :disabled="!pairs.length || loading" @click="saveRows">导出图表数据 · CSV</button></header>
    <p v-if="loading" class="gallery-state" role="status">正在读取表达结果 {{ progress.toLocaleString() }} / {{ total.toLocaleString() }} 个基因…</p>
    <p v-else-if="error" class="gallery-state" role="alert">{{ error }} <button class="btn btn-sm" @click="retry++">重新读取</button></p>
    <template v-else-if="pairs.length">
      <div class="response-stats"><div><strong>{{ pairs.length.toLocaleString() }}</strong><span>{{ truncated ? '已加载基因（部分结果）' : '本次图表基因' }}</span></div><div><strong class="up">{{ up.toLocaleString() }}</strong><span>均值上升</span></div><div><strong class="down">{{ down.toLocaleString() }}</strong><span>均值下降</span></div><div><strong>{{ (complete.length-up-down).toLocaleString() }}</strong><span>均值不变 · 缺失 {{ pairs.length-complete.length }}</span></div></div>
      <p class="scope-note">{{ units || '表达尺度以原记录为准' }} · 变化为 {{ targetLabel }} − 对照；方向与幅度是描述性结果，不表示统计显著性。</p>
      <SingleCellAtlas :record-id="recordId" :kind="sourceKind==='run'?'prediction':'measured'" :genes="atlasGenes" :selected="selected" :read-only="readOnly" @select="inspectAtlasGene" />
      <details class="aggregate-details"><summary>基因变化排行与两组均值对比 <span>群体汇总视图</span></summary><div class="response-plots">
        <section class="response-chart"><header><div><h3>主要响应基因</h3><p>按均值差绝对值展示前 {{ ranked.length }} 项</p></div><button class="btn btn-sm" @click="savePlot('ranking')">SVG</button></header><div class="chart-controls"><button :aria-pressed="mode==='bars'" @click="mode='bars'">变化排行</button><button :aria-pressed="mode==='heatmap'" @click="mode='heatmap'">表达热图</button><label class="sr-only" for="response-direction">变化方向</label><select id="response-direction" v-model="direction"><option value="all">全部方向</option><option value="up">均值上升</option><option value="down">均值下降</option></select></div>
          <div class="response-svg-scroll"><svg ref="barPlot" xmlns="http://www.w3.org/2000/svg" width="550" :height="95+ranked.length*30" :viewBox="`0 0 550 ${95+ranked.length*30}`" font-family="Arial, Microsoft YaHei, sans-serif" font-size="12" fill="#24453b" role="img" aria-label="主要基因变化与表达热图"><title>{{ mode==='bars' ? '基因均值变化排行' : '基因群体均值热图' }}</title><desc>{{ recordId }}；{{ sourceKind }}；{{ units }}；全体已加载基因中按绝对均值差取前 {{ ranked.length }} 个，方向筛选 {{ direction }}。不表示显著性。</desc><rect width="550" height="100%" fill="#fcfdf9" rx="10"/>
          <template v-if="mode==='bars'"><text x="190" y="25" fill="#25816c">下降</text><text x="375" y="25" fill="#ad7139">上升</text><line x1="310" x2="310" y1="40" :y2="45+ranked.length*30" stroke="#b2c4b6"/><text x="310" :y="77+ranked.length*30" text-anchor="middle">均值差 · 共享尺度 ±{{ scoreLabel(maxDelta) }}</text></template>
          <template v-else><text x="228" y="25" text-anchor="middle">对照</text><text x="360" y="25" text-anchor="middle">{{ targetLabel }}</text><text x="18" :y="77+ranked.length*30" fill="#647d72">浅 → 深：{{ scoreLabel(domain.lo) }} → {{ scoreLabel(domain.hi) }} · 群体均值共同色阶</text></template>
          <g v-for="(row,index) in ranked" :key="row.id" :transform="`translate(0 ${40+index*30})`" role="button" tabindex="0" :aria-label="`查看 ${row.id} 表达分布`" @click="choose(row.id)" @keydown.enter="choose(row.id)" @keydown.space.prevent="choose(row.id)" class="response-gene"><title>{{ row.id }}；对照 {{ scoreLabel(row.control) }}；{{ targetLabel }} {{ scoreLabel(row.target) }}；差 {{ scoreLabel(row.delta,true) }}</title><rect x="8" width="534" height="28" rx="5" :fill="selected===row.id?'#e5efe4':'transparent'"/><text x="18" y="18">{{ row.id.length>18 ? row.id.slice(0,18)+'…' : row.id }}</text>
          <rect v-if="mode==='bars'" :x="row.delta!<0 ? 310-Math.abs(row.delta!)/maxDelta*125 : 310" y="7" :width="Math.abs(row.delta!)/maxDelta*125" height="13" rx="3" :fill="color(row.delta)"/>
          <template v-else><rect x="170" width="116" height="25" rx="3" :fill="heat(row.control)"/><rect x="302" width="116" height="25" rx="3" :fill="heat(row.target)"/><text x="228" y="17" text-anchor="middle" :fill="(row.control!-domain.lo)/domain.span>.55?'#fff':'#24453b'">{{ scoreLabel(row.control) }}</text><text x="360" y="17" text-anchor="middle" :fill="(row.target!-domain.lo)/domain.span>.55?'#fff':'#24453b'">{{ scoreLabel(row.target) }}</text></template><text x="527" y="18" text-anchor="end" :fill="color(row.delta)">{{ scoreLabel(row.delta,true) }}</text></g></svg></div>
        </section>
        <section class="response-chart"><header><div><h3>两组表达对比</h3><p>每个点代表一个基因，虚线表示两组均值相等</p></div><button class="btn btn-sm" @click="savePlot('scatter')">SVG</button></header><div class="scatter-legend"><span class="down">● 均值下降</span><span class="up">● 均值上升</span><span>点击点选择基因</span></div><div class="response-svg-scroll"><svg ref="scatterPlot" xmlns="http://www.w3.org/2000/svg" width="550" height="420" viewBox="0 0 550 420" font-family="Arial, Microsoft YaHei, sans-serif" font-size="11" fill="#24453b" role="img" aria-label="对照与扰动基因均值散点图"><title>基因均值：对照与{{ targetLabel }}</title><desc>{{ recordId }}；{{ sourceKind }}；{{ units }}；{{ points.length }}/{{ complete.length }} 个有效基因配对，显示抽样不参与排名或方向统计。</desc><rect width="550" height="420" rx="10" fill="#fcfdf9"/>
          <g v-for="tick in [0,.25,.5,.75,1]" :key="tick"><line x1="62" x2="492" :y1="352-tick*300" :y2="352-tick*300" stroke="#e4eade"/><line :x1="62+tick*430" :x2="62+tick*430" y1="52" y2="352" stroke="#e4eade"/><text x="52" :y="356-tick*300" text-anchor="end">{{ scoreLabel(domain.lo+tick*domain.span) }}</text><text :x="62+tick*430" y="372" text-anchor="middle">{{ scoreLabel(domain.lo+tick*domain.span) }}</text></g>
          <line x1="62" x2="492" y1="352" y2="52" stroke="#9eada2" stroke-dasharray="5 5"/><text x="62" y="28">{{ targetLabel }} · 均值</text><text x="277" y="403" text-anchor="middle">对照 · 均值</text>
          <circle v-for="row in points" :key="row.id" :cx="sx(row.control!)" :cy="sy(row.target!)" r="3" :fill="color(row.delta)" fill-opacity=".5" class="response-point" @click="choose(row.id)"><title>{{ row.id }}：{{ scoreLabel(row.control) }} → {{ scoreLabel(row.target) }}</title></circle>
          <g v-if="current?.control!=null && current?.target!=null"><circle :cx="sx(current.control)" :cy="sy(current.target)" r="6" fill="none" stroke="#204e3d" stroke-width="2"/><text :x="Math.min(420,Math.max(65,sx(current.control)+8))" :y="Math.max(45,sy(current.target)-10)" font-weight="600">{{ current.id }}</text></g>
        </svg></div><p class="scope-note">显示 {{ points.length.toLocaleString() }} / {{ complete.length.toLocaleString() }} 个有效配对{{ points.length<complete.length?'（确定性抽样）':'' }}；排名、方向统计与 CSV 使用全部已加载数据。</p></section>
      </div>
      </details>
      <div ref="genePicker" class="gene-picker" style="scroll-margin-top:100px"><div><span>当前基因</span><strong>{{ selected || '未选择' }}</strong><small v-if="current">对照 {{ scoreLabel(current.control) }} → {{ targetLabel }} {{ scoreLabel(current.target) }} · Δ {{ scoreLabel(current.delta,true) }}</small></div><form @submit.prevent="chooseQuery"><label class="sr-only" :for="`gene-picker-${recordId}`">查找表达基因</label><input :id="`gene-picker-${recordId}`" v-model="query" :list="`gene-options-${recordId}`" placeholder="输入基因名称" type="search"/><datalist :id="`gene-options-${recordId}`"><option v-for="row in options" :key="row.id" :value="row.id"/></datalist><button class="btn btn-sm" :disabled="!options.length">查看分布</button></form><button class="btn btn-sm" :disabled="!selected" @click="emit('select',selected)">在结果表中查看 ↗</button></div>
      <GeneDistribution :control-mean="current?.control" :target-mean="current?.target" :units="units" :kind="sourceKind==='run'?'prediction':'measured'" :record-id="recordId" :gene="selected" :read-only="readOnly"/>
    </template><p v-else class="gallery-state">当前结果没有可用的基因表达数据。</p>
  </section>
</template>
<style scoped>
.expression-gallery{min-width:0;color:var(--ink)}.gallery-heading,.response-chart header{display:flex;justify-content:space-between;align-items:start;gap:16px}.eyebrow{font-size:11px;color:var(--primary);letter-spacing:2px}h2{font-size:25px;font-weight:500;margin:10px 0}h3{font-size:19px;font-weight:500;margin:0}.gallery-heading p,.response-chart header p{font-size:12px;color:var(--muted);line-height:1.8;margin:8px 0 0}.response-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));background:var(--surface-soft);border:1px solid var(--border);border-radius:12px;margin-top:22px;padding:18px 0}.response-stats>div{display:grid;gap:8px;padding:0 20px;border-right:1px solid var(--border)}.response-stats>div:last-child{border:0}.response-stats strong{font-size:26px;font-weight:500}.response-stats span{font-size:12px;color:var(--muted)}.up{color:#ad7139}.down{color:#25816c}.scope-note{font-size:11px;color:var(--muted);line-height:1.8;margin:12px 0}.response-plots{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin-top:20px}.response-chart{min-width:0;border:1px solid var(--border);border-radius:14px;padding:18px}.chart-controls,.scatter-legend{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:18px 0 12px;min-height:33px}.chart-controls button,.chart-controls select{font-size:12px;border:1px solid var(--border);background:var(--card);color:var(--muted);padding:7px 9px;border-radius:6px}.chart-controls button[aria-pressed=true]{background:var(--primary-weak);color:var(--primary-strong);border-color:var(--primary)}.chart-controls select{margin-left:auto}.scatter-legend{font-size:11px;color:var(--muted);gap:14px}.response-svg-scroll{overflow-x:auto}.response-svg-scroll svg{display:block;width:100%;height:auto;min-width:430px}.response-gene,.response-point{cursor:pointer}.response-gene:focus rect:first-child{stroke:#25816c}.response-gene:focus{outline:none}.response-point:hover{r:5;fill-opacity:1}.gene-picker{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;border:1px solid var(--border);background:var(--surface-soft);border-radius:12px;padding:18px;margin-top:22px}.gene-picker>div{display:grid;gap:5px}.gene-picker span,.gene-picker small{font-size:12px;color:var(--muted)}.gene-picker strong{font-size:21px;font-weight:500}.gene-picker form{display:flex;gap:8px;min-width:0}.gene-picker input{min-width:0;width:180px;border:1px solid var(--border);background:var(--card);border-radius:7px;padding:10px;color:var(--ink);font:inherit;font-size:12px}.gallery-state{padding:40px 20px;background:var(--surface-soft);border-radius:12px;color:var(--muted);font-size:13px}@media(max-width:1050px){.response-plots{grid-template-columns:1fr}}@media(max-width:650px){.gallery-heading{flex-direction:column}.response-stats{grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.response-stats strong{font-size:23px}.response-stats>div:nth-child(2){border:0}.response-chart{padding:12px}.gene-picker input{width:145px}.gene-picker{padding:14px}h2{font-size:22px}}
.aggregate-details{margin-top:20px;border:1px solid var(--border);border-radius:12px;padding:16px}.aggregate-details>summary{cursor:pointer;color:var(--primary-strong);font-size:14px}.aggregate-details>summary span{font-size:12px;color:var(--muted);margin-left:12px}
</style>
