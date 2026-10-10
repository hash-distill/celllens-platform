<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ParamPanel from '../components/ParamPanel.vue'
import StageProgress from '../components/StageProgress.vue'
import EvidenceSidebar from '../components/EvidenceSidebar.vue'
import ResponseWorkspace from '../components/response/ResponseWorkspace.vue'
import MetabolismWorkspace from '../components/function/MetabolismWorkspace.vue'
import CellStateTab from '../components/tabs/CellStateTab.vue'
import GenesTab from '../components/tabs/GenesTab.vue'
import ValidationTab from '../components/tabs/ValidationTab.vue'
import { useRunStore } from '../stores/run'
import { useRecentStore } from '../stores/recent'
import { useCandidatesStore } from '../stores/candidates'
import { useDraftStore } from '../stores/draft'
import { useUiStore } from '../stores/ui'
import { api } from '../api/client'
import { downloadBlob } from '../utils/csv'
import { runSourceLabel } from '../utils/source'
import { STATUS_LABEL, fmtServerTime } from '../utils/format'
const route = useRoute(), router = useRouter()
const runs = useRunStore(), recent = useRecentStore(), candidates = useCandidatesStore()
const draft = useDraftStore(), ui = useUiStore()
const runId = computed(() => typeof route.query.run === 'string' ? route.query.run : '')
const entry = computed(() => runId.value ? runs.entry(runId.value) : null)
const record = computed(() => entry.value?.record)
const editing = ref(false), downloading = ref(false), resubmitting = ref(false)
const reportNote = ref('')
const tabs = [{key:'response',label:'响应概览'},{key:'cell',label:'单细胞状态'},{key:'genes',label:'基因响应'},{key:'metabolism',label:'代谢功能'},{key:'validation',label:'预测验证'}] as const
const activeTab = computed(() => route.query.tab === 'function' ? 'metabolism' : tabs.some(tab => tab.key === route.query.tab) ? String(route.query.tab) : 'response')
watch(() => route.query.tab, tab => { if(tab==='function') void router.replace({path:route.path,query:{...route.query,tab:'metabolism',view:'function'}}) }, {immediate:true})
watch(runId, id => { editing.value=!id; reportNote.value=''; if(id) runs.openRun(id); else runs.leaveRun() }, {immediate:true})
watch(record, rec => { if(rec) recent.add({run_id:rec.run_id,cell_line:rec.request.cell_line,perturbation:rec.request.perturbation,mode:rec.request.mode,status:rec.status}) }, {immediate:true})
watch([() => record.value?.status, activeTab], ([status,tab]) => {if(status==='completed' && tab!=='response' && tab!=='cell') runs.ensureTabData(runId.value,tab)}, {immediate:true})
onBeforeUnmount(() => runs.leaveRun())
function selectTab(tab:string) { void router.replace({path:'/workbench',query:{run:runId.value,tab:tab==='response'?undefined:tab}}) }
function fillDraft() { if(record.value) { draft.applyFromRequest(record.value.request); editing.value=true; ui.push('info','已复用本次参数，可在上方调整并提交新实验') } }
function addCandidate() { if(record.value) { const result=candidates.add(runId.value,record.value.request); ui.push(result.ok?'success':'warning',result.ok?'已加入实验比较，可从顶部进入比较页':result.reason ?? '无法加入比较') } }
async function downloadReport() { if(record.value?.status!=='completed' || downloading.value)return; downloading.value=true; reportNote.value=''; try {const result=await api.downloadReport(runId.value);downloadBlob(result.blob,result.filename)} catch(error) {reportNote.value=error instanceof Error?error.message:'报告下载失败'} finally {downloading.value=false} }
async function resubmit() { if(!record.value || resubmitting.value)return;resubmitting.value=true;try {const result=await runs.createRun({...record.value.request});if(result) await router.push({path:'/workbench',query:{run:result.run_id}});else ui.push('error',runs.submitError?.message ?? '重新提交失败')}finally{resubmitting.value=false} }
</script>
<template>
  <div class="page workbench-page">
    <header class="page-heading"><div><span class="eyebrow">EXPERIMENT WORKBENCH</span><h1>实验工作台</h1><p>设置实验，跟踪计算，并在同一工作台分析结果。</p></div><div class="btn-row"><RouterLink to="/records" class="btn">实验记录</RouterLink><RouterLink v-if="runId" to="/workbench" class="btn btn-primary">新建实验</RouterLink></div></header>
    <details class="workspace-configuration" :open="editing" @toggle="editing=($event.target as HTMLDetailsElement).open"><summary><span>{{ runId ? '下一次实验设置' : '实验设置' }}</span><small>{{ runId ? '修改参数不会改变当前结果' : '选择细胞背景、扰动与运行模式' }}</small><span class="configuration-toggle">{{ editing ? '收起' : '展开' }}</span></summary><ParamPanel destination="workbench" horizontal /></details>
    <section v-if="!runId" class="workspace-empty"><span class="eyebrow">READY FOR A NEW QUESTION</span><h2>从一个基因扰动开始。</h2><p>提交后在这里跟踪运行进度，完成后查看单细胞状态、基因响应和代谢结果。</p><RouterLink to="/records">打开已有实验 →</RouterLink></section>
    <section v-else class="workspace-results" aria-label="本次实验分析">
      <header class="active-experiment"><div><span class="eyebrow">CURRENT EXPERIMENT</span><h2 v-if="record">{{ record.request.cell_line }} / {{ record.request.perturbation }} 扰动实验 <span class="pill pill-neutral">{{ STATUS_LABEL[record.status] }}</span></h2><h2 v-else>读取实验记录</h2><p class="run-identity mono">{{ runId }}</p><p v-if="record" class="experiment-meta">{{ runSourceLabel(record.request.mode,runId,record.result_kind) }} · {{ record.request.mode === 'precomputed' ? '读取已保存结果' : '请求 '+record.request.n_cells+' 个预测细胞' }} · {{ fmtServerTime(record.created_at) }}</p></div><div class="experiment-actions btn-row"><button class="btn btn-sm" @click="runs.refreshRecord(runId)">刷新状态</button><button v-if="record" class="btn btn-sm" @click="fillDraft">复用参数</button><button v-if="record?.status==='completed'" class="btn btn-sm" :disabled="candidates.has(runId)" @click="addCandidate">{{ candidates.has(runId)?'已加入比较':'加入比较' }}</button><button v-if="record?.status==='completed'" class="btn btn-sm" :disabled="downloading" @click="downloadReport">{{ downloading?'下载中…':'导出报告' }}</button><RouterLink v-if="record?.status==='completed'" :to="{path:'/demo',query:{run:runId}}" class="btn btn-primary btn-sm">解读本次实验</RouterLink></div></header>
      <div v-if="entry?.notFound" class="card"><h2>运行不存在</h2><p>请检查运行编号，或从实验记录中打开其他实验。</p><RouterLink to="/records" class="btn">查看实验记录</RouterLink></div>
      <div v-else-if="!record" class="card"><p>{{ entry?.recordError ? '运行记录读取失败：'+entry.recordError.message : '正在读取所选实验…' }}</p><button v-if="entry?.recordError" class="btn" @click="runs.refreshRecord(runId)">重试运行记录</button></div>
      <template v-else>
        <p v-if="entry?.recordError" class="notice notice-warn">{{ entry.recordError.message }}</p><p v-if="reportNote" class="notice notice-warn">{{ reportNote }}</p>
        <StageProgress v-if="record.status!=='completed'" :record="record" :poll-issue="entry?.pollIssue" />
        <div v-if="record.status==='failed'" class="card"><h2>本次分析失败</h2><p>{{ record.error_message || '请检查运行来源与错误记录。' }}</p><button class="btn btn-primary" :disabled="resubmitting" @click="resubmit">{{ resubmitting?'提交中…':'以相同参数重新运行' }}</button></div>
        <template v-if="record.status==='completed'"><div class="tabs result-tabs" role="tablist" aria-label="分析结果"><button v-for="tab in tabs" :key="tab.key" class="tab" :class="{active:activeTab===tab.key}" role="tab" :aria-selected="activeTab===tab.key" @click="selectTab(tab.key)">{{ tab.label }}</button></div><ResponseWorkspace v-if="activeTab==='response'" :key="runId" :run-id="runId" /><MetabolismWorkspace v-else-if="activeTab==='metabolism'" :key="runId" :run-id="runId" /><div v-else class="card analysis-panel"><CellStateTab v-if="activeTab==='cell'" :key="runId" :run-id="runId" /><GenesTab v-else-if="activeTab==='genes'" :run-id="runId" /><ValidationTab v-else :run-id="runId" /></div></template>
        <details v-if="entry" class="run-evidence"><summary>运行来源、数据覆盖与解释边界</summary><EvidenceSidebar :entry="entry" /></details>
      </template>
    </section>
  </div>
</template>
<style scoped>
.workspace-configuration{border:1px solid var(--border);background:var(--card);margin-bottom:24px}.workspace-configuration>summary{display:flex;align-items:center;gap:16px;padding:18px 24px;cursor:pointer;font-size:13px;color:var(--primary);list-style:none}.workspace-configuration>summary small{font-size:11px;color:var(--muted)}.configuration-toggle{margin-left:auto;font-size:10px}.workspace-configuration :deep(.param-panel>.card){border:0;border-top:1px solid var(--border);margin:0}.workspace-empty{padding:66px 24px;border-top:1px solid var(--border);text-align:center}.workspace-empty h2{font-size:26px;font-weight:500;margin:16px 0}.workspace-empty p{font-size:12px;color:var(--muted);line-height:1.9}.workspace-empty a{font-size:12px;display:inline-block;margin-top:14px}.active-experiment{display:flex;justify-content:space-between;gap:24px;align-items:center;padding:24px;background:var(--card);border:1px solid var(--border);margin-bottom:20px}.active-experiment h2{font-size:22px;font-weight:500;margin:10px 0}.active-experiment .pill{font-size:10px;margin-left:12px;vertical-align:middle}.run-identity{font-size:10px;color:var(--muted);overflow-wrap:anywhere;margin:0}.experiment-meta{font-size:10px;color:var(--muted);line-height:1.9;margin:8px 0 0}.experiment-actions{max-width:370px;justify-content:flex-end}.result-tabs{margin-bottom:20px;overflow-x:auto;flex-wrap:nowrap;white-space:nowrap}.analysis-panel{margin-top:0}.run-evidence{margin-top:20px;border:1px solid var(--border);background:var(--card)}.run-evidence>summary{padding:16px 24px;cursor:pointer;font-size:12px;color:var(--primary)}.run-evidence :deep(.card){border:0;margin:0}@media(max-width:900px){.active-experiment{flex-direction:column;align-items:start}.experiment-actions{justify-content:flex-start;max-width:none}}@media(max-width:600px){.workspace-configuration>summary{padding:16px;gap:10px;flex-wrap:wrap}.workspace-configuration>summary small{order:3;flex-basis:100%}.active-experiment{padding:18px}.active-experiment h2{font-size:19px}.workspace-empty{padding:35px 12px}.workspace-empty h2{font-size:23px}.result-tabs .tab{font-size:11px;padding:10px 12px}}
</style>
