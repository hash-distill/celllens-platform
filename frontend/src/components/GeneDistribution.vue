<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { openChartAssistant, assistantFigure } from '../stores/assistantSource'
import { scoreLabel } from '../utils/metabolicVisualization'
import { apiFetch } from '../api/http'
import { downloadBlob } from '../utils/csv'
const props = defineProps<{ kind: 'measured' | 'prediction'; recordId: string; gene: string; readOnly?: boolean; controlMean?: number | null; targetMean?: number | null; units?:string }>()
type Context = { genes: string[]; availability: { distribution: boolean }; reasons?: { distribution?: string } }
watch(() => props.gene, (gene, previous) => {if(assistantFigure.value?.chart_type === 'distribution' && assistantFigure.value.feature_id === previous) assistantFigure.value = {...assistantFigure.value,feature_id:gene}})
const context = ref<Context | null>(null), contextError = ref(''), error = ref(''), loading = ref(false), retry = ref(0)
const url = ref(''), svg = ref<Blob | null>(null)
const endpoint = computed(() => `/figures/${props.kind}/${encodeURIComponent(props.recordId)}`)
watch([endpoint, () => props.readOnly, retry], async (_, _old, cleanup) => {
  const control = new AbortController(); cleanup(() => control.abort())
  context.value = null; contextError.value = ''
  if (props.readOnly) return
  try { const result = await apiFetch<Context>(`${endpoint.value}/context`, {signal: control.signal}); if (!control.signal.aborted) context.value = result }
  catch (e) { if (!control.signal.aborted) contextError.value = e instanceof Error ? e.message : '表达数据来源读取失败' }
}, { immediate: true })
const available = computed(() => Boolean(context.value?.availability.distribution && context.value.genes.includes(props.gene)))
watch([endpoint, () => props.gene, available, retry], (_, _old, cleanup) => {
  const control = new AbortController()
  if (url.value) URL.revokeObjectURL(url.value)
  url.value = ''; svg.value = null; error.value = ''; loading.value = false
  const path = endpoint.value, gene = props.gene
  const timer = window.setTimeout(async () => {
    if (!available.value || !gene) return
    loading.value = true
    try {
      const blob = await apiFetch<Blob>(`${path}/render`, { method: 'POST', body: {chart:'distribution',gene,group:'all',embedding:'pca',title:'',note:'',direction:'both',limit:10}, query:{format:'svg'}, responseType:'blob', signal:control.signal, timeoutMs:120000 })
      if (control.signal.aborted) return
      if (!(blob instanceof Blob) || !blob.type.startsWith('image/svg+xml') || !/<svg[\s>]/i.test(await blob.slice(0,1024).text())) throw new Error('服务没有返回有效的表达分布图')
      if (!control.signal.aborted) { svg.value = blob; url.value = URL.createObjectURL(blob) }
    } catch(e) { if (!control.signal.aborted) error.value = e instanceof Error ? e.message : '分布图读取失败' }
    finally { if (!control.signal.aborted) loading.value = false }
  }, 180)
  cleanup(() => { control.abort(); clearTimeout(timer); if(url.value) URL.revokeObjectURL(url.value) })
}, { immediate: true })
function save() { if(svg.value) downloadBlob(svg.value, `${props.recordId}_gene-distribution.svg`) }
</script>
<template>
  <section class="gene-distribution" aria-label="单基因逐细胞表达分布">
    <header><div><span class="eyebrow">SINGLE GENE / SINGLE CELL</span><h3>{{ gene || '选择基因' }} <small>对照与扰动表达比较</small></h3></div><div class="distribution-actions"><button class="btn btn-sm" :disabled="!svg" @click="openChartAssistant({view:'chart',chart_type:'distribution',feature_kind:'gene',feature_id:gene})">AI 解读这张图</button><button class="btn btn-sm" :disabled="!svg" @click="save">导出分布图 · SVG</button></div></header>
    <div class="reading-guide"><div><strong>先看位置，再看分散程度</strong><p>纵轴越高，表达值越大。<b>橙线是中位数</b>；箱体包含中间 50% 的细胞；散点表示单个细胞，横向位置只是避免重叠。</p></div><div v-if="controlMean!=null && targetMean!=null"><strong>{{ gene }} · 当前群体均值</strong><p>对照 {{ scoreLabel(controlMean) }} → {{ kind==='prediction'?'模型预测':'扰动实测' }} {{ scoreLabel(targetMean) }}，差值 <b>{{ scoreLabel(targetMean-controlMean,true) }}</b>。</p><small>{{ units || '尺度见纵轴' }} · 均值与图中橙线的中位数不同。</small></div></div>
    <p v-if="readOnly" class="distribution-state">当前公开视图未开放逐细胞图表读取。</p>
    <div v-else-if="contextError || error" class="distribution-state" role="alert">{{ contextError || error }} <button class="btn btn-sm" @click="retry++">重试</button></div>
    <p v-else-if="!gene" class="distribution-state">点击上方基因或输入名称，查看表达分布。</p>
    <p v-else-if="!context || loading || (available && !url)" class="distribution-state" role="status">正在读取 {{ gene }} 的逐细胞表达…</p>
    <p v-else-if="!available" class="distribution-state">{{ context.reasons?.distribution && !context.availability.distribution ? context.reasons.distribution : '本次结果未保存该基因的逐细胞表达，仍可查看上方群体均值。' }}</p>
    <img v-else :src="url" :alt="`${gene} 的逐细胞表达箱线图与散点`" />
    <p class="distribution-caption">各组为当前记录中保存的群体；细胞数量和表达尺度以图中标注为准。该分布图不提供独立生物学重复的显著性检验。</p>
  </section>
</template>
<style scoped>
.gene-distribution{min-width:0;border-top:1px solid var(--border);padding-top:24px;margin-top:24px}header{display:flex;align-items:center;justify-content:space-between;gap:16px}.eyebrow{font-size:11px;letter-spacing:2px;color:var(--primary)}h3{font-size:24px;font-weight:500;margin:10px 0}h3 small{font-size:14px;color:var(--muted);margin-left:10px}.distribution-caption{font-size:12px;line-height:1.9;color:var(--muted)}img{display:block;width:100%;max-height:530px;object-fit:contain;background:#fff;border-radius:12px;border:1px solid var(--border)}.distribution-state{padding:35px 20px;background:var(--surface-soft);border-radius:12px;font-size:13px;color:var(--muted);line-height:1.8}@media(max-width:650px){header{align-items:start;flex-direction:column}h3 small{display:block;margin:8px 0}}
.distribution-actions{display:flex;gap:8px;flex-wrap:wrap}.reading-guide{display:grid;grid-template-columns:1.2fr 1fr;gap:24px;background:var(--surface-soft);border:1px solid var(--border);border-radius:12px;padding:18px 20px;margin:16px 0}.reading-guide strong{font-size:14px;font-weight:500}.reading-guide p,.reading-guide small{font-size:12px;line-height:1.9;color:var(--muted);margin:7px 0 0}.reading-guide b{font-weight:500;color:var(--ink)}img{max-height:440px}@media(max-width:650px){.reading-guide{grid-template-columns:1fr;gap:12px}}
</style>
