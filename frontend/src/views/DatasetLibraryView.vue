<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch, ApiError } from '../api/http'
import { accessSession } from '../stores/access'

type Dataset = {id:string; title:string; version:string; status:string; cell_count:number|null; total_cell_count:number|null; condition_count:number|null; source:Record<string,unknown>; preparation?:string; status_reason?:string; inspection?:{excluded_unassigned_control_cells?:number}}
type Condition = {id:string; label:string; cell_line:string; perturbation:string; dose:number|string|null; dose_unit:string|null; time:number|string|null; time_unit:string|null; control_type:string; control_label?:string; cell_count:number; control_cell_count:number; analysis_available:boolean}
const route=useRoute(),router=useRouter()
const datasets=ref<Dataset[]>([]), selected=ref(''), items=ref<Condition[]>([]), total=ref(0), page=ref(1)
const query=ref(''), applied=ref(''), catalogLoading=ref(false), conditionsLoading=ref(false), catalogError=ref(''), conditionError=ref('')
const sending=ref(''), actionError=ref(''), uncertain=ref(false), maxCells=ref(256), seed=ref(42), refresh=ref(0)
const readOnly=computed(()=>Boolean(accessSession.value?.read_only))
const dataset=computed(()=>datasets.value.find(item=>item.id===selected.value))
const loading=computed(()=>catalogLoading.value||conditionsLoading.value)
const error=computed(()=>catalogError.value||conditionError.value)
const pages=computed(()=>Math.max(1,Math.ceil(total.value/10)))
let catalogController:AbortController|undefined, controller:AbortController|undefined, submissionController:AbortController|undefined
const message=(e:unknown)=>e instanceof Error?e.message:'读取失败，请重试'
function count(value:number|null|undefined){return value==null?'未核验':value.toLocaleString()}
function quantity(value:number|string|null,unit:string|null,label:string){return value==null||value===''?`${label}未记录`:`${value} ${unit?.trim()||'（单位未记录）'}`}
function controlLabel(condition:Condition){
  return ['zero_dose_same_drug_label','source_zero_dose'].includes(condition.control_type)?'同一药物标签 · 零剂量对照（非已核实 DMSO）'
    :condition.control_type==='source_annotated_control_unverified_vehicle'?'源标注对照 · 溶剂未核实':condition.control_label||`源对照类型：${condition.control_type||'未记录'}`
}
function cancelSubmission(){
  if(sending.value){submissionController?.abort();sending.value='';uncertain.value=true;actionError.value='提交确认已中断，任务可能已创建；请先到实验记录核对。'}
}
async function loadDatasets(){
  if(readOnly.value)return
  catalogController?.abort();controller?.abort();const current=catalogController=new AbortController()
  catalogLoading.value=true;catalogError.value='';conditionError.value='';items.value=[];total.value=0
  try{
    const result=await apiFetch<{items:Dataset[]}>('/datasets',{signal:current.signal})
    if(current.signal.aborted||readOnly.value)return
    datasets.value=result.items
    const requested=typeof route.query.dataset==='string'?route.query.dataset:''
    const next=requested||selected.value||result.items[0]?.id||''
    if(next&&!result.items.some(item=>item.id===next)){selected.value='';catalogError.value='指定数据集未登记，请从已登记来源重新选择。';return}
    selected.value=next;refresh.value++
  }catch(e){if(!current.signal.aborted){datasets.value=[];selected.value='';catalogError.value=message(e)}}
  finally{if(!current.signal.aborted)catalogLoading.value=false}
}
watch(selected,()=>{controller?.abort();items.value=[];total.value=0;page.value=1;cancelSubmission()},{flush:'sync'})
watch([selected,page,applied,refresh],async()=>{
  controller?.abort();const current=controller=new AbortController(),identity=selected.value
  items.value=[];total.value=0;conditionError.value='';conditionsLoading.value=false
  if(!identity||readOnly.value)return
  conditionsLoading.value=true
  try{
    const result=await apiFetch<{items:Condition[];total:number}>(`/datasets/${encodeURIComponent(identity)}/conditions`,{query:{limit:10,offset:(page.value-1)*10,query:applied.value},signal:current.signal})
    if(current.signal.aborted||readOnly.value||selected.value!==identity)return
    const last=Math.max(1,Math.ceil(result.total/10))
    if(page.value>last){page.value=last;return}
    items.value=result.items;total.value=result.total
  }catch(e){if(!current.signal.aborted)conditionError.value=message(e)}
  finally{if(!current.signal.aborted)conditionsLoading.value=false}
})
watch(()=>route.query.dataset,value=>{
  if(readOnly.value)return
  const requested=typeof value==='string'?value:''
  if(datasets.value.some(item=>item.id===requested)){catalogError.value='';selected.value=requested}
  else if(requested&&!catalogLoading.value){selected.value='';catalogError.value='指定数据集未登记，请从已登记来源重新选择。'}
})
function search(){if(sending.value)return;controller?.abort();page.value=1;applied.value=query.value.trim();refresh.value++}
function retryLoad(){if(catalogError.value||!selected.value)void loadDatasets();else refresh.value++}
async function analyse(condition:Condition){
  if(sending.value||uncertain.value||readOnly.value||loading.value||!selected.value||!condition.analysis_available||!items.value.some(item=>item.id===condition.id))return
  if(!Number.isInteger(maxCells.value)||maxCells.value<1||maxCells.value>4096||!Number.isInteger(seed.value)||seed.value<0||seed.value>2147483647){actionError.value='请输入范围内的整数采样数和随机种子';return}
  const current=submissionController=new AbortController(),identity=selected.value
  sending.value=condition.id;actionError.value=''
  try{
    const result=await apiFetch<{id:string}>(`/datasets/${encodeURIComponent(identity)}/analyses`,{method:'POST',body:{condition_id:condition.id,max_cells:maxCells.value,seed:seed.value},signal:current.signal})
    if(!current.signal.aborted&&!readOnly.value&&identity===selected.value)await router.push(`/measured/${encodeURIComponent(result.id)}`)
  }catch(e){if(!current.signal.aborted){actionError.value=message(e);uncertain.value=e instanceof ApiError&&['network','timeout'].includes(e.kind)}}
  finally{if(!current.signal.aborted)sending.value=''}
}
watch(readOnly,()=>{
  catalogController?.abort();controller?.abort();cancelSubmission();datasets.value=[];selected.value='';items.value=[];total.value=0
  catalogLoading.value=false;conditionsLoading.value=false;catalogError.value='';conditionError.value=''
  if(!readOnly.value)void loadDatasets()
},{immediate:true,flush:'sync'})
onBeforeUnmount(()=>{catalogController?.abort();controller?.abort();submissionController?.abort()})
</script>

<template>
  <main class="dataset-library">
    <header class="library-heading"><div><p class="eyebrow">EXPERIMENTAL DATA LIBRARY</p><h1>从药物处理，观察细胞响应</h1><p>选择可追溯的公开研究条件，比较真实单细胞表达与通路变化。</p></div><RouterLink class="quiet-link" to="/data-catalog">基因扰动目录 ↗</RouterLink></header>
    <p v-if="readOnly" class="notice">公开展示模式仅开放已发布研究案例。<RouterLink to="/records?status=completed">查看案例</RouterLink></p>
    <template v-else>
      <div v-if="error" role="alert" class="notice error">{{ error }} <button @click="retryLoad">重试</button></div>
      <section v-if="dataset" class="dataset-card">
        <div><span class="tag">公开实测 · 药物扰动</span><h2>{{ dataset.title }}</h2><p>固定版本 {{ dataset.version }} · 对照与处理组分别保留来源，分析时冻结实际输入。</p><p v-if="dataset.status!=='ready'" class="preparation-state" role="status">数据尚未准备完成，当前不能提交分析。请联系工作区维护者完成来源准备与校验。</p><details><summary>研究来源与数据版本</summary><dl><template v-for="(value,key) in dataset.source" :key="key"><dt>{{ key }}</dt><dd>{{ value }}</dd></template><template v-if="dataset.status!=='ready'"><dt>准备说明</dt><dd>{{ dataset.preparation||'等待工作区维护者准备数据' }}</dd><dt>当前状态</dt><dd>{{ dataset.status_reason||'来源文件尚未通过准备校验' }}</dd></template></dl></details></div>
        <div class="dataset-metrics"><div><strong>{{ count(dataset.total_cell_count ?? dataset.cell_count) }}</strong><span>源数据细胞</span></div><div><strong>{{ count(dataset.condition_count) }}</strong><span>已登记处理条件</span></div></div>
        <p v-if="dataset.inspection?.excluded_unassigned_control_cells" class="dataset-exclusions">来源核查排除了 {{ dataset.inspection.excluded_unassigned_control_cells.toLocaleString() }} 个无法分配到明确药物标签的对照细胞；这些细胞不参与本页条件比较。</p>
      </section>
      <section class="condition-panel" aria-label="药物研究条件">
        <div class="panel-title"><div><p class="eyebrow">SELECT A CONTRAST</p><h2>选择处理条件</h2></div><span>实测组间描述性分析</span></div>
        <form class="filters" @submit.prevent="search"><label v-if="datasets.length>1">数据集<select v-model="selected" :disabled="Boolean(sending)"><option v-for="item in datasets" :key="item.id" :value="item.id">{{ item.title }}</option></select></label><label class="search">查找药物或细胞背景<input v-model="query" :disabled="Boolean(sending)" type="search" placeholder="输入药物名称、细胞或条件" maxlength="200" /></label><button type="submit" :disabled="Boolean(sending)||catalogLoading">筛选条件</button></form>
        <div class="sampling"><label>每组最多采样<input v-model.number="maxCells" :disabled="Boolean(sending)" type="number" min="1" max="4096" step="1" /></label><label>随机种子<input v-model.number="seed" :disabled="Boolean(sending)" type="number" min="0" max="2147483647" step="1" /></label><p>从选定条件与匹配对照中固定抽样；不会生成新的实测细胞。</p></div>
        <p v-if="actionError" role="alert" class="notice error">{{ actionError }} <RouterLink v-if="uncertain" to="/records">提交状态不确定，先到实验记录核对</RouterLink></p>
        <p v-if="loading" role="status" class="empty">正在读取研究条件…</p>
        <p v-else-if="!items.length&&!error" class="empty">{{ datasets.length?'没有匹配的研究条件，请调整筛选。':'尚未登记可用数据集。完成数据准备后可在此选择研究条件。' }}</p>
        <div v-else-if="!error" class="table-wrap"><table><thead><tr><th>处理 / 细胞背景</th><th>剂量与时间</th><th>处理 / 对照细胞</th><th>研究入口</th></tr></thead><tbody><tr v-for="condition in items" :key="condition.id"><td><strong>{{ condition.perturbation }}</strong><small>{{ condition.cell_line }}</small></td><td>{{ quantity(condition.dose,condition.dose_unit,'剂量') }}<small>{{ quantity(condition.time,condition.time_unit,'处理时间') }}</small></td><td>{{ condition.cell_count.toLocaleString() }} / {{ condition.control_cell_count.toLocaleString() }}<small>{{ controlLabel(condition) }}</small></td><td><button :disabled="!condition.analysis_available||Boolean(sending)||uncertain" @click="analyse(condition)">{{ sending===condition.id?'正在提交…':condition.analysis_available?'分析实测响应':'条件暂不可分析' }}</button></td></tr></tbody></table></div>
        <footer class="pagination"><span>共 {{ total.toLocaleString() }} 条 · 10 条 / 页 · 第 {{ page }} / {{ pages }} 页</span><button :disabled="page<=1||loading||Boolean(sending)" @click="page--">上一页</button><button :disabled="page>=pages||loading||Boolean(sending)" @click="page++">下一页</button></footer>
      </section>
      <aside class="method-note"><strong>怎样理解这些结果</strong><p>单细胞数量不等于独立生物学重复数。表达差异与通路富集用于提出后续验证假设，不直接证明药物疗效或作用机制。具体对照标注、物种、剂量和版本可在分析结果中核对。</p></aside>
    </template>
  </main>
</template>

<style scoped>
.dataset-library{max-width:1320px;margin:auto;padding:42px 28px 70px;color:var(--ink)}.library-heading{display:flex;justify-content:space-between;align-items:center;gap:25px;margin-bottom:30px}.eyebrow{font-size:11px;letter-spacing:.16em;color:var(--primary);margin:0 0 12px}h1{font-size:clamp(26px,3vw,38px);font-weight:500;margin:0 0 14px}h2{font-size:23px;font-weight:500;margin:14px 0}p{line-height:1.85;color:var(--muted);margin:8px 0}.quiet-link{color:var(--primary);white-space:nowrap}.dataset-card{display:grid;grid-template-columns:1.5fr 1fr;gap:32px;padding:30px;border:1px solid var(--border);background:linear-gradient(120deg,var(--primary-weak),var(--card));border-radius:18px;margin-bottom:28px}.tag{font-size:12px;color:var(--primary)}.dataset-metrics{display:grid;grid-template-columns:1fr 1fr;align-content:center;gap:20px}.dataset-metrics div{border-left:1px solid var(--border);padding-left:24px}.dataset-metrics strong{font:38px Georgia,serif;color:var(--primary)}.dataset-metrics span{display:block;font-size:12px;color:var(--muted);margin-top:10px}details{margin-top:16px;font-size:12px;color:var(--muted)}summary{cursor:pointer;color:var(--primary)}dl{display:grid;grid-template-columns:100px 1fr;gap:10px}dd{margin:0;overflow-wrap:anywhere}.condition-panel{padding:28px;background:var(--card);border:1px solid var(--border);border-radius:18px}.panel-title{display:flex;justify-content:space-between;align-items:center}.panel-title>span{color:var(--muted);font-size:12px}.filters{display:flex;gap:12px;align-items:end;margin:15px 0}.filters label{display:grid;gap:8px;font-size:12px;color:var(--muted)}.search{flex:1}.sampling{display:flex;flex-wrap:wrap;gap:18px;align-items:center;padding:16px 0;border-bottom:1px solid var(--border)}.sampling label{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:10px}.sampling input{width:105px}.sampling p{font-size:12px}input,select{padding:11px 12px;border:1px solid var(--border);border-radius:8px;background:var(--field-bg);color:var(--ink);min-width:0}button{padding:10px 16px;border:1px solid var(--border);border-radius:9px;background:var(--card);color:var(--primary);cursor:pointer;white-space:nowrap}td button,.filters button{background:var(--primary);color:white;border-color:var(--primary)}button:disabled{opacity:.45;cursor:not-allowed}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;color:var(--muted);font-weight:500;background:var(--surface-soft);padding:16px}td{padding:18px 16px;border-bottom:1px solid var(--border)}td small{display:block;color:var(--muted);font-size:11px;margin-top:7px}.pagination{display:flex;gap:12px;align-items:center;margin-top:20px;font-size:12px;color:var(--muted)}.pagination span{margin-right:auto}.method-note{margin-top:24px;padding:0 6px;font-size:12px;color:var(--muted)}.method-note p{max-width:960px}.notice,.empty{padding:25px;border-radius:10px;background:var(--surface-soft)}.error{color:var(--danger)}.empty{text-align:center;margin:20px 0}@media(max-width:700px){.dataset-library{padding:25px 16px}.library-heading,.panel-title{align-items:start;flex-direction:column;gap:12px}.dataset-card{grid-template-columns:1fr;padding:22px;gap:20px}.condition-panel{padding:16px}.sampling{gap:12px}.sampling p{margin:0}.pagination{flex-wrap:wrap}.pagination span{width:100%}table{min-width:600px}.filters{flex-wrap:wrap}.filters .search{min-width:190px}}
</style>


<style scoped>.dataset-exclusions{grid-column:1/-1;margin:0;font-size:12px;padding-top:15px;border-top:1px solid var(--border)}</style>
