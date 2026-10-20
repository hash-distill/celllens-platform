<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listExperiments } from '../api/experiments'
import { isMockEnabled } from '../api/mockFlag'
import { useCandidatesStore } from '../stores/candidates'
import { useUiStore } from '../stores/ui'
import { STATUS_LABEL, fmtServerTime } from '../utils/format'
import type { ExperimentQuery, ExperimentList, ExperimentRecord } from '../types/experiment'
const route=useRoute(), router=useRouter(), candidates=useCandidatesStore(), ui=useUiStore()
const data=ref<ExperimentList|null>(null), loading=ref(false), error=ref('')
const search=ref(''), status=ref<ExperimentQuery['status']>('all')
const mock=isMockEnabled()
const limit=computed(() => [10,20,50,100].includes(Number(route.query.size))?Number(route.query.size):20)
const page=computed(() => {const value=Number(route.query.page);return Number.isInteger(value)&&value>0&&value<=20000?value:1})
const pageCount=computed(() => Math.max(1,Math.ceil((data.value?.total??0)/limit.value)))
let controller:AbortController|undefined
async function load() {
  controller?.abort(); const current=new AbortController(); controller=current
  loading.value=true; error.value=''
  try {const result=await listExperiments({limit:limit.value,offset:(page.value-1)*limit.value,q:typeof route.query.q==='string'?route.query.q.trim():'',status:['active','completed','failed'].includes(String(route.query.status))?route.query.status as ExperimentQuery['status']:'all'},current.signal);if(!current.signal.aborted)data.value=result}
  catch(reason){if(!current.signal.aborted)error.value=reason instanceof Error?reason.message:'实验记录读取失败'}
  finally{if(!current.signal.aborted)loading.value=false}
}
watch(() => route.fullPath, () => {
  search.value=typeof route.query.q==='string'?route.query.q:''
  status.value=['active','completed','failed'].includes(String(route.query.status))?route.query.status as ExperimentQuery['status']:'all'
  void load()
},{immediate:true})
onBeforeUnmount(() => controller?.abort())
function applyFilters(){void router.push({path:'/records',query:{size:route.query.size,q:search.value.trim()||undefined,status:status.value==='all'?undefined:status.value}});if(page.value===1 && search.value.trim()===(route.query.q??'') && status.value===(route.query.status??'all'))void load()}
function movePage(value:number){void router.push({path:'/records',query:{...route.query,page:value===1?undefined:String(value)}})}
function changeSize(event:Event){void router.push({path:'/records',query:{...route.query,page:undefined,size:(event.target as HTMLSelectElement).value}})}
function target(record:ExperimentRecord){return {path:'/demo',query:{run:record.id}}}
function addCandidate(record:ExperimentRecord){if(!record.run)return;const result=candidates.add(record.id,record.run.request);ui.push(result.ok?'success':'warning',result.ok?'已加入比较，可从顶部进入实验比较':result.reason??'无法加入比较')}
</script>
<template>
  <div class="page records-page">
    <header class="page-heading"><div><span class="eyebrow">EXPERIMENT RECORDS</span><h1>实验记录</h1><p>{{ mock?'开发数据记录 · 保存在当前浏览器':'在线推演结果保存于服务器，随时查看运行状态与分析结果。' }}</p></div><div class="btn-row"><RouterLink to="/workbench" class="btn btn-primary">新建实验</RouterLink></div></header>
    <section class="records-panel" aria-label="实验记录列表">
      <form class="record-filters" @submit.prevent="applyFilters"><div class="search-field"><label class="label" for="record-search">检索实验</label><input id="record-search" v-model="search" class="input" maxlength="128" placeholder="搜索细胞背景、扰动基因或编号" /></div><div><label class="label" for="record-status">运行状态</label><select id="record-status" v-model="status" class="select"><option value="all">全部状态</option><option value="active">进行中</option><option value="completed">已完成</option><option value="failed">失败</option></select></div><button class="btn btn-primary" type="submit">检索</button><button class="btn" type="button" :disabled="loading" @click="load">刷新记录</button></form>
      <div class="records-count"><span>{{ loading?'正在读取…':error?'记录读取失败':`共 ${data?.total??0} 个实验` }}</span><span>按创建时间倒序 · {{ mock?'本浏览器 Mock 存储':'服务器数据库' }}</span></div>
      <div v-if="error" class="records-empty" role="alert"><h2>实验记录读取失败</h2><p>{{ error }}</p><button class="btn" @click="load">重试记录</button></div>
      <div v-else-if="loading" class="records-empty" role="status">正在加载实验记录…</div>
      <div v-else-if="!data?.items.length" class="records-empty"><h2>{{ search || status!=='all' ? '没有符合条件的实验' : '还没有实验记录' }}</h2><p>{{ search || status!=='all' ? '调整检索条件，或在检索框搜索运行编号。' : '从工作台创建实验后，记录会显示在这里。' }}</p><RouterLink to="/workbench" class="btn">新建实验</RouterLink></div>
      <div v-else class="records-table-wrap"><table class="records-table"><thead><tr><th scope="col">实验编号</th><th scope="col">结果来源</th><th scope="col">运行状态</th><th scope="col">创建时间</th><th scope="col">操作</th></tr></thead><tbody><tr v-for="record in data.items" :key="record.id" :data-run-id="record.id"><td><RouterLink :to="target(record)" class="record-title">{{ record.title }}</RouterLink><span class="record-id mono">{{ record.id }}</span><small>{{ record.subtitle }}</small></td><td><span class="record-source">{{ mock?'Mock 在线推演':'在线推演' }}</span></td><td><span class="record-status" :class="record.status">{{ STATUS_LABEL[record.status] }}</span><small v-if="record.run && record.status!=='completed' && record.status!=='failed'">进度 {{ record.run?.stage_progress }}%</small></td><td class="record-time">{{ fmtServerTime(record.created_at) }}</td><td><div class="record-actions"><RouterLink :to="target(record)" class="btn btn-sm">实验分析</RouterLink><button v-if="record.status==='completed'" class="btn btn-ghost btn-sm" :disabled="candidates.has(record.id)" @click="addCandidate(record)">{{ candidates.has(record.id)?'已选比较':'加入比较' }}</button></div></td></tr></tbody></table></div>
      <footer v-if="!error && data?.total" class="record-pagination"><span>第 {{ page }} / {{ pageCount }} 页</span><div class="btn-row"><label class="sr-only" for="record-size">每页条数</label><select id="record-size" :value="limit" class="select" style="width:auto;font-size:10px" @change="changeSize"><option value="10">10 条 / 页</option><option value="20">20 条 / 页</option><option value="50">50 条 / 页</option><option value="100">100 条 / 页</option></select><button class="btn btn-sm" :disabled="page===1 || loading" @click="movePage(page-1)">上一页</button><button class="btn btn-sm" :disabled="page>=pageCount || loading" @click="movePage(page+1)">下一页</button></div></footer>
    </section>
  </div>
</template>
<style scoped>
.records-panel{background:var(--card);border:1px solid var(--border)}.record-filters{display:grid;grid-template-columns:minmax(180px,1fr) 145px auto auto;gap:12px;align-items:end;padding:24px}.record-filters .label{font-size:11px}.record-filters .input,.record-filters .select{font-size:12px;min-height:38px}.record-filters .btn{min-height:38px;font-size:12px}.records-count{display:flex;justify-content:space-between;gap:15px;border-top:1px solid var(--border);padding:15px 24px;color:var(--muted);font-size:10px}.records-count>span:first-child{color:var(--primary)}.records-table-wrap{overflow-x:auto}.records-table{width:100%;border-collapse:collapse;text-align:left}.records-table th{background:var(--table-head-bg);color:var(--muted);font-size:10px;font-weight:500;padding:12px 20px;white-space:nowrap}.records-table td{padding:20px;border-bottom:1px solid var(--border);font-size:11px;vertical-align:middle}.record-title{display:block;font-size:13px;font-weight:500;min-width:180px}.record-id{display:block;font-size:9px;color:var(--muted);margin:7px 0;overflow-wrap:anywhere}.records-table small{display:block;font-size:9px;color:var(--muted);margin-top:7px}.record-source{display:block;max-width:130px;font-size:10px;line-height:1.8}.record-time{max-width:180px;font-size:10px!important;line-height:1.8;color:var(--muted)}.record-status{display:inline-block;padding:4px 8px;background:var(--surface-tint);font-size:10px;color:var(--primary);white-space:nowrap}.record-status.failed{color:var(--danger);background:var(--danger-bg)}.record-status.completed{background:var(--ok-bg);color:var(--ok)}.record-actions{display:flex;gap:5px;flex-wrap:wrap}.record-actions .btn{font-size:10px;white-space:nowrap}.records-empty{text-align:center;padding:55px 24px;color:var(--muted);font-size:12px}.records-empty h2{font-size:20px;font-weight:500;color:var(--ink)}.records-empty p{margin:15px 0 24px}.record-pagination{display:flex;align-items:center;justify-content:space-between;padding:18px 24px;gap:12px;font-size:10px;color:var(--muted)}@media(max-width:900px){.record-filters{grid-template-columns:1fr 1fr}.search-field{grid-column:1/-1}}@media(max-width:600px){.record-filters{padding:18px;gap:12px}.records-count{padding:15px 18px;flex-wrap:wrap}.records-table th,.records-table td{padding:14px}.record-title{font-size:12px}.record-pagination{padding:16px 18px}}
</style>
