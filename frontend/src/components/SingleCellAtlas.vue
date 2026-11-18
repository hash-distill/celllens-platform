<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { openChartAssistant, assistantFigure } from '../stores/assistantSource'
import { apiFetch } from '../api/http'
import { downloadBlob, downloadCsv } from '../utils/csv'
import { scoreLabel } from '../utils/metabolicVisualization'
type Group = {source:string;count:number;displayed:number;genes:Array<{gene:string;mean:number;positive_fraction:number}>}
interface Atlas {record_id:string;kind:string;genes:string[];units:string;groups:Group[];cells:Array<{cell_id:string;source:string;values:number[]}>;value_domain:[number,number];sampling:Record<string,unknown>;provenance:Record<string,unknown>}
const props=defineProps<{recordId:string;kind:'measured'|'prediction';genes:string[];selected?:string;readOnly?:boolean}>()
const emit=defineEmits<{select:[gene:string]}>()
const view=ref<'heatmap'|'dotplot'>('heatmap'), data=shallowRef<Atlas|null>(null), loading=ref(false), error=ref(''), retry=ref(0)
watch([view,()=>props.selected],()=>{const current=assistantFigure.value;if(current && ['heatmap','dotplot'].includes(current.chart_type ?? '')) assistantFigure.value={...current,chart_type:view.value,feature_id:props.selected || props.genes[0]}})
const plot=ref<SVGSVGElement|null>(null)
const names:Record<string,string>={control:'实测对照',observed:'扰动实测',predicted:'模型预测'}
const groupColor:Record<string,string>={control:'#92a69b',observed:'#25816c',predicted:'#bb8845'}
const geneKey=computed(()=>JSON.stringify(props.genes.slice(0,20)))
watch([()=>props.recordId,()=>props.kind,()=>props.readOnly,geneKey,retry],async(_, _old,cleanup)=>{
 const control=new AbortController();cleanup(()=>control.abort());data.value=null;error.value='';loading.value=false
 if(props.readOnly || !props.genes.length)return
 loading.value=true
 try{
  const result=await apiFetch<Atlas>(`/figures/${props.kind}/${encodeURIComponent(props.recordId)}/expression-atlas`,{method:'POST',body:{genes:JSON.parse(geneKey.value),cells_per_group:150},signal:control.signal,timeoutMs:120000})
  if(control.signal.aborted)return
  if(result.record_id!==props.recordId || result.kind!==props.kind || JSON.stringify(result.genes)!==geneKey.value)throw new Error('图谱来源与当前研究不一致')
  data.value=result
 }catch(e){if(!control.signal.aborted)error.value=e instanceof Error?e.message:'图谱读取失败'}
 finally{if(!control.signal.aborted)loading.value=false}
},{immediate:true})
watch(()=>props.recordId,()=>{view.value='heatmap'})
const groups=computed(()=>{
 let start=0
 return (data.value?.groups??[]).map(group=>{const item={...group,start};start+=group.displayed;return item})
})
const dotX=(index:number)=>180+(index+.5)*760/Math.max(1,groups.value.length)
const height=computed(()=>145+(data.value?.genes.length??0)*32)
const cellWidth=computed(()=>760/Math.max(1,data.value?.cells.length??0))
const meanMax=computed(()=>Math.max(.000001,...(data.value?.groups??[]).flatMap(group=>group.genes.map(gene=>gene.mean))))
const meanMin=computed(()=>Math.min(0,...(data.value?.groups??[]).flatMap(group=>group.genes.map(gene=>gene.mean))))
function heat(value:number,max:number,min=0){const t=Math.max(0,Math.min(1,(value-min)/(max-min||1)));return `rgb(${Math.round(243-211*t)},${Math.round(247-139*t)},${Math.round(234-151*t)})`}
function saveSvg(){if(!plot.value)return;const copy=plot.value.cloneNode(true) as SVGSVGElement;copy.setAttribute('xmlns','http://www.w3.org/2000/svg');downloadBlob(new Blob([new XMLSerializer().serializeToString(copy)],{type:'image/svg+xml;charset=utf-8'}),`${props.recordId}_single-cell-${view.value}.svg`)}
function saveData(){if(data.value)downloadBlob(new Blob([JSON.stringify(data.value,null,2)],{type:'application/json'}),`${props.recordId}_single-cell-atlas.json`)}
function saveCsv(){if(!data.value)return;const d=data.value;if(view.value==='dotplot')downloadCsv(`${props.recordId}_expression-groups.csv`,['研究记录','群体','总细胞数','基因','平均表达','表达值大于0的比例','尺度'],d.groups.flatMap(g=>g.genes.map(x=>[props.recordId,g.source,g.count,x.gene,x.mean,x.positive_fraction,d.units])));else downloadCsv(`${props.recordId}_heatmap-displayed-cells.csv`,['研究记录','群体','细胞标识',...d.genes],d.cells.map(c=>[props.recordId,c.source,c.cell_id,...c.values]))}
</script>
<template>
 <section class="single-cell-atlas" aria-label="单细胞响应图谱">
  <header><div><span class="eyebrow">SINGLE-CELL RESPONSE ATLAS</span><h3>单细胞响应图谱</h3><p>比较当前选定的 {{ genes.length }} 个基因；点击基因可继续查看表达分布。</p></div><div class="atlas-actions"><button class="btn btn-sm" :disabled="!data" @click="openChartAssistant({view:'chart',chart_type:view,feature_kind:'gene',feature_id:selected || genes[0]})">AI 解读{{ selected || genes[0] }}</button><button class="btn btn-sm" :disabled="!data" @click="saveSvg">导出图像 · SVG</button><button class="btn btn-sm" :disabled="!data" @click="saveCsv">{{ view==='heatmap'?'图中细胞 CSV':'群体统计 CSV' }}</button><button class="btn btn-sm" :disabled="!data" @click="saveData">图谱数据 JSON</button></div></header>
  <div class="atlas-tabs" role="group" aria-label="单细胞图谱视图"><button :aria-pressed="view==='heatmap'" @click="view='heatmap'">基因 × 细胞热图</button><button :aria-pressed="view==='dotplot'" @click="view='dotplot'">群体表达气泡图</button></div>
  <p v-if="readOnly" class="atlas-state">公开视图未开放逐细胞图谱读取。</p>
  <p v-else-if="loading" class="atlas-state" role="status">正在读取冻结的逐细胞表达，计算各群体统计…</p>
  <div v-else-if="error" class="atlas-state" role="alert"><p>{{ error }}</p><button class="btn btn-sm" @click="retry++">重新读取</button></div>
  <template v-else-if="data">
   <div class="group-counts"><span v-for="group in groups" :key="group.source"><i :style="{background:groupColor[group.source]}"/>{{ names[group.source] }} <strong>{{ group.count.toLocaleString() }}</strong> 个细胞<small v-if="view==='heatmap'"> · 显示 {{ group.displayed }}</small></span></div>
   <p class="atlas-note">{{ view==='heatmap'?'每列一个细胞，每行一个基因；按群体分区，组内按细胞标识排序，不表示时间顺序。':'气泡颜色表示群体平均表达，面积表示表达值大于 0 的细胞比例；使用全部已保存细胞计算。' }} 点击基因查看下方分布。</p>
   <div class="cell-atlas-scroll"><svg ref="plot" xmlns="http://www.w3.org/2000/svg" width="1000" :height="height" :viewBox="`0 0 1000 ${height}`" font-family="Arial, Microsoft YaHei, sans-serif" font-size="12" fill="#24453b" role="img" :aria-label="view==='heatmap'?'基因乘细胞表达热图':'群体表达气泡图'"><title>{{ view==='heatmap'?'单细胞表达热图':'群体表达气泡图' }}</title><desc>{{ recordId }}；{{ kind }}；{{ data.units }}；热图最多每群体150个细胞按标识排序等间隔抽样；气泡统计来自全部冻结细胞，正值阈值0。未做基因逐行标准化。</desc><rect width="1000" :height="height" rx="12" fill="#fcfdf9"/>
    <template v-if="view==='heatmap'"><g v-for="group in groups" :key="group.source"><rect :x="180+group.start*cellWidth" y="42" :width="group.displayed*cellWidth-2" height="7" rx="2" :fill="groupColor[group.source]"/><text :x="180+(group.start+group.displayed/2)*cellWidth" y="27" text-anchor="middle">{{ names[group.source] }} · {{ group.displayed }}/{{ group.count }}</text></g></template>
    <template v-else><text v-for="(group,gi) in groups" :key="group.source" :x="dotX(gi)" y="29" text-anchor="middle">{{ names[group.source] }} · n={{ group.count }}</text></template>
    <g v-for="(gene,index) in data.genes" :key="gene" :transform="`translate(0 ${62+index*32})`" class="cell-gene" role="button" tabindex="0" :aria-label="`查看 ${gene} 表达分布`" @click="emit('select',gene)" @keydown.enter="emit('select',gene)" @keydown.space.prevent="emit('select',gene)"><rect x="8" y="-2" width="975" height="31" rx="4" :fill="selected===gene?'#e3eddf':index%2?'#f3f6ef':'transparent'"/><text x="18" y="18" :font-weight="selected===gene?'600':'400'">{{ gene.length>21?gene.slice(0,21)+'…':gene }}</text><title>{{ gene }} · 点击查看逐细胞分布</title>
     <template v-if="view==='heatmap'"><rect v-for="(cell,ci) in data.cells" :key="`${cell.source}-${cell.cell_id}`" :x="180+ci*cellWidth" y="0" :width="cellWidth+.15" height="26" :fill="heat(cell.values[index]!,data.value_domain[1],data.value_domain[0])"><title>{{ gene }} · {{ names[cell.source] }} · {{ cell.cell_id }} · {{ scoreLabel(cell.values[index]!) }} {{ data.units }}</title></rect></template>
     <template v-else><g v-for="(group,gi) in groups" :key="group.source"><circle :cx="dotX(gi)" cy="12" :r="Math.sqrt(group.genes[index]!.positive_fraction)*13" :fill="heat(group.genes[index]!.mean,meanMax,meanMin)" stroke="#96b5a2" stroke-width=".7"><title>{{ gene }} · {{ names[group.source] }} · 平均表达 {{ scoreLabel(group.genes[index]!.mean) }} · 数值大于0 {{ (group.genes[index]!.positive_fraction*100).toFixed(1) }}% · n={{ group.count }}</title></circle><text :x="dotX(gi)+23" y="16" font-size="10" fill="#647d72">{{ (group.genes[index]!.positive_fraction*100).toFixed(0) }}%</text></g></template>
    </g>
    <text x="18" :y="height-24" font-size="11" fill="#647d72">{{ data.units }} · 统一原始表达色阶；未做逐行标准化</text><g v-for="step in 60" :key="step"><rect :x="530+step*3" :y="height-36" width="3" height="12" :fill="heat(step/60,1)"/></g><text x="520" :y="height-25" text-anchor="end">{{ scoreLabel(view==='heatmap'?data.value_domain[0]:meanMin) }}</text><text x="727" :y="height-25">{{ scoreLabel(view==='heatmap'?data.value_domain[1]:meanMax) }}</text><text v-if="view==='dotplot'" x="820" :y="height-25" font-size="11">圆面积 ∝ 正值细胞比例</text>
   </svg></div>
   <p class="atlas-note">{{ view==='heatmap'?'热图抽样仅用于控制显示密度；图中细胞 CSV 与热图一致，完整群体统计保存在图谱 JSON 中。':'正值比例依赖测序检测和表达处理；模型预测中的正值比例不等于实验检测率。' }}</p>
  </template><p v-else class="atlas-state">请选择有表达记录的基因。</p>
 </section>
</template>
<style scoped>
.single-cell-atlas{margin-top:24px;min-width:0;border:1px solid var(--border);border-radius:14px;padding:22px;background:var(--card)}header{display:flex;justify-content:space-between;gap:20px;align-items:start}.eyebrow{font-size:11px;letter-spacing:2px;color:var(--primary)}h3{font-size:24px;font-weight:500;margin:9px 0}header p,.atlas-note{font-size:12px;color:var(--muted);line-height:1.9}.atlas-actions,.atlas-tabs{display:flex;gap:8px;flex-wrap:wrap}.atlas-tabs{margin:22px 0 18px;padding-bottom:16px;border-bottom:1px solid var(--border)}.atlas-tabs button{border:1px solid var(--border);background:transparent;color:var(--muted);border-radius:8px;padding:10px 14px;font:inherit;font-size:13px;cursor:pointer}.atlas-tabs button[aria-pressed=true]{color:var(--on-primary);background:var(--primary);border-color:var(--primary)}.group-counts{display:flex;gap:20px;flex-wrap:wrap;font-size:12px;color:var(--muted)}.group-counts span{display:flex;align-items:center;gap:6px}.group-counts i{width:7px;height:7px;border-radius:50%}.group-counts strong{color:var(--ink)}.cell-atlas-scroll{overflow:auto;border:1px solid var(--border);border-radius:10px}.cell-atlas-scroll svg{width:100%;height:auto;min-width:800px;display:block}.cell-gene{cursor:pointer}.cell-gene:focus{outline:none}.cell-gene:focus>rect:first-child,.cell-gene:hover>rect:first-child{stroke:#25816c;stroke-width:1}.atlas-state{padding:30px 15px;color:var(--muted);background:var(--surface-soft);font-size:13px;line-height:1.8}.structure-view{min-width:0}@media(max-width:700px){.single-cell-atlas{padding:14px}header{flex-direction:column}.atlas-tabs button{font-size:12px;padding:8px 10px}h3{font-size:22px}}
</style>
