<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ParamPanel from '../components/ParamPanel.vue'
import StageProgress from '../components/StageProgress.vue'
import EvidenceSidebar from '../components/EvidenceSidebar.vue'
import RunResultOverview from '../components/RunResultOverview.vue'
import MetabolismWorkspace from '../components/function/MetabolismWorkspace.vue'
import CellStateTab from '../components/tabs/CellStateTab.vue'
import GenesTab from '../components/tabs/GenesTab.vue'
import ValidationTab from '../components/tabs/ValidationTab.vue'
import MeasuredComparisonTab from '../components/tabs/MeasuredComparisonTab.vue'
import { useRunStore } from '../stores/run'
import { useRecentStore } from '../stores/recent'
import { useCandidatesStore } from '../stores/candidates'
import { useDraftStore } from '../stores/draft'
import { useUiStore } from '../stores/ui'
import { api } from '../api/client'
import type { CellLine } from '../types/run'
import { downloadBlob } from '../utils/csv'
import { isSyntheticResult, runSourceLabel } from '../utils/source'
import { STATUS_LABEL, fmtServerTime } from '../utils/format'
import { useAssistantSource, openAssistant } from '../stores/assistantSource'
const route = useRoute(), router = useRouter()
const props = defineProps<{resultsOnly?: boolean}>()
const runs = useRunStore(), recent = useRecentStore(), candidates = useCandidatesStore()
const draft = useDraftStore(), ui = useUiStore()
const runId = computed(() => typeof route.params.runId === 'string' ? route.params.runId : typeof route.query.run === 'string' ? route.query.run : '')
watch([() => route.query.cell_line, () => route.query.perturbation, runId], ([cellLine, perturbation, id]) => {
  if (props.resultsOnly || id) return
  if (typeof cellLine === 'string' && ['K562', 'RPE1', 'Jurkat', 'HepG2'].includes(cellLine)) draft.setCellLine(cellLine as CellLine)
  if (typeof perturbation === 'string') {
    const target = perturbation.trim().toUpperCase()
    if (target.length <= 128 && /^[A-Z0-9][A-Z0-9._-]*$/.test(target)) draft.perturbation = target
  }
}, { immediate: true })
const entry = computed(() => runId.value ? runs.entry(runId.value) : null)
const record = computed(() => entry.value?.record)
const editing = ref(false), downloading = ref(false), resubmitting = ref(false)
const overviewMatched = ref(false)
const reportNote = ref('')
const packageKind = ref<'analysis'|'single-cell'|'network'|'ranking'>('analysis')
const packageDownloading = ref(false), packageNote = ref('')
let reportController: AbortController | undefined, packageController: AbortController | undefined
const packageUnavailable = computed(() => !record.value || record.value.status !== 'completed' ? '实验完成后可导出结果包'
  : isSyntheticResult(record.value.request.mode,runId.value,record.value.result_kind) ? '合成数据暂不支持结果包导出'
  : record.value.request.mode === 'validation' || activeTab.value === 'comparison' ? '实测对比请使用下方的完整对比 CSV 或来源 JSON' : '')
const tabs = [{key:'overview',label:'结果概览'},{key:'genes',label:'基因响应'},{key:'metabolism',label:'代谢功能'},{key:'comparison',label:'实测对比'}]
const activeTab = computed(() => route.query.tab === 'function' ? 'metabolism' : route.query.tab === 'cell' || route.query.tab === 'validation' ? String(route.query.tab) : tabs.some(tab => tab.key === route.query.tab) ? String(route.query.tab) : 'overview')
useAssistantSource(() => record.value ? {
  kind:'run', id:runId.value, title:`${record.value.request.cell_line} · ${record.value.request.perturbation}`,
  completed:record.value.status === 'completed',
  view:activeTab.value === 'genes' ? 'genes' : activeTab.value === 'metabolism' ? 'metabolism' : activeTab.value === 'comparison' || (activeTab.value === 'overview' && overviewMatched.value) ? 'comparison' : 'overview',
} : null)
watch(() => route.query.tab, tab => { if(tab==='function') void router.replace({path:route.path,query:{...route.query,tab:'metabolism',view:'function'}}) }, {immediate:true})
watch(runId, id => { overviewMatched.value=false;reportController?.abort();packageController?.abort();downloading.value=false;packageDownloading.value=false;packageNote.value='';editing.value=!id; reportNote.value=''; if(id) runs.openRun(id); else runs.leaveRun() }, {immediate:true,flush:'sync'})
watch(activeTab, () => {packageController?.abort();packageDownloading.value=false;packageNote.value=''}, {flush:'sync'})
watch(record, rec => { if(rec) recent.add({run_id:rec.run_id,cell_line:rec.request.cell_line,perturbation:rec.request.perturbation,mode:rec.request.mode,status:rec.status}) }, {immediate:true})
watch([() => record.value?.status, activeTab], ([status,tab]) => {if(status==='completed' && tab!=='overview' && tab!=='cell' && tab!=='comparison') runs.ensureTabData(runId.value,tab)}, {immediate:true})
onBeforeUnmount(() => {reportController?.abort();packageController?.abort();runs.leaveRun()})
function selectTab(tab:string) { void router.replace({path:route.path,query:{run:typeof route.params.runId === 'string' ? undefined : runId.value,tab:tab==='overview'?undefined:tab}}) }
function fillDraft() { if(record.value) { draft.applyFromRequest(record.value.request); if(props.resultsOnly) void router.push('/research?type=prediction'); else editing.value=true; ui.push('info','已复用本次参数，可调整并提交新实验') } }
function addCandidate() { if(record.value) { const result=candidates.add(runId.value,record.value.request); ui.push(result.ok?'success':'warning',result.ok?'已加入比较，可从“结果解读”的“预测结果比较”进入':result.reason ?? '无法加入比较') } }
async function downloadReport() { if(record.value?.status!=='completed' || downloading.value)return; const id=runId.value,current=reportController=new AbortController();downloading.value=true; reportNote.value=''; try {const result=await api.downloadReport(id,current.signal);if(!current.signal.aborted && id===runId.value)downloadBlob(result.blob,result.filename)} catch(error) {if(!current.signal.aborted)reportNote.value=error instanceof Error?error.message:'报告下载失败'} finally {if(!current.signal.aborted)downloading.value=false} }
async function downloadPackage() {
  if (packageUnavailable.value || packageDownloading.value) return
  const id=runId.value,chosen=packageKind.value,current=packageController=new AbortController()
  packageDownloading.value=true;packageNote.value=''
  try {
    const result=await api.getExportPackage(id,chosen,current.signal)
    if(!current.signal.aborted && id===runId.value) downloadBlob(result.blob,result.filename)
  } catch(error) {if(!current.signal.aborted)packageNote.value=error instanceof Error?error.message:'结果包下载失败'}
  finally {if(!current.signal.aborted)packageDownloading.value=false}
}
async function resubmit() { if(!record.value || resubmitting.value)return;resubmitting.value=true;try {const result=await runs.createRun({...record.value.request, mode:'online'});if(result) await router.push({path:'/workbench',query:{run:result.run_id}});else ui.push('error',runs.submitError?.message ?? '重新提交失败')}finally{resubmitting.value=false} }
</script>
<template>
  <div class="page workbench-page" :class="{'has-run': Boolean(runId)}">
    <header v-if="!props.resultsOnly" class="page-heading"><div><span class="eyebrow">MODEL PREDICTION WORKBENCH</span><h1>模型预测工作台</h1><p>明确运行模型预测，分析生成的扰动表达，并与可用实测进行比较。</p></div><div class="btn-row"><RouterLink to="/measured" class="btn">实测分析</RouterLink><RouterLink to="/records?category=predicted" class="btn">预测记录</RouterLink><RouterLink v-if="runId" to="/workbench" class="btn btn-primary">新建预测</RouterLink></div></header>
    <details v-if="!props.resultsOnly" class="workspace-configuration" :open="editing" @toggle="editing=($event.target as HTMLDetailsElement).open"><summary><span>{{ runId ? '下一次实验设置' : '实验设置' }}</span><small>{{ runId ? '修改参数不会改变当前结果' : '选择细胞背景、扰动与采样参数' }}</small><span class="configuration-toggle">{{ editing ? '收起' : '展开' }}</span></summary><ParamPanel destination="workbench" horizontal /></details>
    <section v-if="!runId" class="workspace-empty"><span class="eyebrow">EXPLICIT MODEL PREDICTION</span><h2>按研究问题选择预测。</h2><p>预测完成后可分析生成的表达与代谢评分；当前固定源缺少实测，不代表全球未测，也不证明模型已验证泛化。</p><div class="btn-row workspace-empty-links"><RouterLink to="/data-catalog">先查询数据覆盖 →</RouterLink><RouterLink to="/records?view=results&amp;category=predicted">解读已有预测 →</RouterLink></div></section>
    <section v-else class="workspace-results" aria-label="本次实验分析">
      <header class="active-experiment"><div><span class="eyebrow">CURRENT EXPERIMENT</span><component :is="props.resultsOnly ? 'h1' : 'h2'" v-if="record">{{ record.request.cell_line }} / {{ record.request.perturbation }} 扰动实验 <span class="pill pill-neutral">{{ STATUS_LABEL[record.status] }}</span></component><h2 v-else>读取实验记录</h2><p class="run-identity mono">{{ runId }}</p><p v-if="record" class="experiment-meta">{{ runSourceLabel(record.request.mode,runId,record.result_kind) }} · {{ record.request.mode === 'precomputed' ? '读取已保存结果' : '请求 '+record.request.n_cells+' 个预测细胞' }} · {{ fmtServerTime(record.created_at) }}</p></div><div class="experiment-actions btn-row"><RouterLink v-if="props.resultsOnly" to="/records" class="btn btn-sm">实验记录</RouterLink><button class="btn btn-sm" @click="runs.refreshRecord(runId)">刷新状态</button><button v-if="record" class="btn btn-sm" @click="fillDraft">复用参数</button><button v-if="record?.status==='completed'" class="btn btn-sm" :disabled="candidates.has(runId)" @click="addCandidate">{{ candidates.has(runId)?'已加入比较':'加入比较' }}</button><button v-if="record?.status==='completed'" class="btn btn-sm" :disabled="downloading" @click="downloadReport">{{ downloading?'下载中…':'导出 PDF 报告' }}</button><div v-if="record?.status==='completed'" class="package-export"><select v-model="packageKind" aria-label="导出结果包类型" :disabled="packageDownloading || !!packageUnavailable"><option value="analysis">分析结果包 ZIP</option><option value="single-cell">单细胞分析包 ZIP</option><option value="network">网络包 ZIP</option><option value="ranking">基因排序包 ZIP</option></select><button class="btn btn-sm" :disabled="packageDownloading || !!packageUnavailable" :title="packageUnavailable || undefined" @click="downloadPackage">{{ packageDownloading?'下载中…':'下载结果包' }}</button></div></div></header>
      <p v-if="packageUnavailable && record?.status==='completed'" class="muted small">{{ packageUnavailable }}</p><p v-if="packageNote" class="notice notice-warn" role="alert">{{ packageNote }}</p>
      <div v-if="entry?.notFound" class="card"><h2>运行不存在</h2><p>请检查运行编号，或从实验记录中打开其他实验。</p><RouterLink to="/records" class="btn">查看实验记录</RouterLink></div>
      <div v-else-if="!record" class="card"><p>{{ entry?.recordError ? '运行记录读取失败：'+entry.recordError.message : '正在读取所选实验…' }}</p><button v-if="entry?.recordError" class="btn" @click="runs.refreshRecord(runId)">重试运行记录</button></div>
      <template v-else>
        <p v-if="entry?.recordError" class="notice notice-warn">{{ entry.recordError.message }}</p><p v-if="reportNote" class="notice notice-warn">{{ reportNote }}</p>
        <StageProgress v-if="record.status!=='completed'" :record="record" :poll-issue="entry?.pollIssue" />
        <div v-if="record.status==='failed'" class="card"><h2>本次分析失败</h2><p>{{ record.error_message || '请检查运行来源与错误记录。' }}</p><button class="btn btn-primary" :disabled="resubmitting" @click="resubmit">{{ resubmitting?'提交中…':'以相同参数重新运行' }}</button></div>
        <template v-if="record.status==='completed'"><div v-if="activeTab!=='overview'" class="result-interpretation"><span>结合当前结果，解释图表与数据变化</span><button type="button" class="btn btn-sm" @click="openAssistant(false)">解读当前结果</button></div><div class="tabs result-tabs" role="tablist" aria-label="分析结果"><button v-for="tab in tabs" :key="tab.key" class="tab" :class="{active:activeTab===tab.key}" role="tab" :aria-selected="activeTab===tab.key" @click="selectTab(tab.key)">{{ tab.label }}</button></div><p v-if="['genes','metabolism'].includes(activeTab)" class="muted small">本页为原运行群体；匹配后的三组比较见“实测对比”。</p><RunResultOverview v-if="activeTab==='overview'" :key="runId" :run-id="runId" @comparison-mode="overviewMatched = $event" /><MetabolismWorkspace v-else-if="activeTab==='metabolism'" :key="runId" :run-id="runId" /><div v-else class="card analysis-panel"><CellStateTab v-if="activeTab==='cell'" :key="runId" :run-id="runId" /><GenesTab v-else-if="activeTab==='genes'" :run-id="runId" /><MeasuredComparisonTab v-else-if="activeTab==='comparison'" :key="runId" :run-id="runId" /><ValidationTab v-else :run-id="runId" /></div></template>
        <details v-if="entry" class="run-evidence"><summary>实验参数与数据来源</summary><EvidenceSidebar :entry="entry" /></details>
      </template>
    </section>
  </div>
</template>
<style scoped>
.result-interpretation{display:flex;align-items:center;justify-content:flex-end;gap:16px;margin:20px 0 10px;font-size:12px;color:var(--muted)}
.workspace-configuration{border:1px solid var(--border);background:var(--card);margin-bottom:24px}.workspace-configuration>summary{display:flex;align-items:center;gap:16px;padding:18px 24px;cursor:pointer;font-size:13px;color:var(--primary);list-style:none}.workspace-configuration>summary small{font-size:11px;color:var(--muted)}.configuration-toggle{margin-left:auto;font-size:10px}.workspace-configuration :deep(.param-panel>.card){border:0;border-top:1px solid var(--border);margin:0}.workspace-empty{padding:66px 24px;border-top:1px solid var(--border);text-align:center}.workspace-empty h2{font-size:26px;font-weight:500;margin:16px 0}.workspace-empty p{font-size:12px;color:var(--muted);line-height:1.9}.workspace-empty a{font-size:12px;display:inline-block;margin-top:14px}.active-experiment{display:flex;justify-content:space-between;gap:24px;align-items:center;padding:24px;background:var(--card);border:1px solid var(--border);margin-bottom:20px}.active-experiment h1,.active-experiment h2{font-size:22px;font-weight:500;margin:10px 0}.active-experiment .pill{font-size:10px;margin-left:12px;vertical-align:middle}.run-identity{font-size:10px;color:var(--muted);overflow-wrap:anywhere;margin:0}.experiment-meta{font-size:10px;color:var(--muted);line-height:1.9;margin:8px 0 0}.experiment-actions{max-width:430px;justify-content:flex-end}.result-tabs{margin-bottom:20px;overflow-x:auto;flex-wrap:nowrap;white-space:nowrap}.analysis-panel{margin-top:0}.run-evidence{margin-top:20px;border:1px solid var(--border);background:var(--card)}.run-evidence>summary{padding:16px 24px;cursor:pointer;font-size:12px;color:var(--primary)}.run-evidence :deep(.card){border:0;margin:0}
.package-export{display:flex;gap:6px;align-items:center}.package-export select{border:1px solid var(--border);background:var(--card);color:var(--ink);padding:7px;font:11px var(--font);max-width:190px}.package-export select:disabled{opacity:.55}
.workspace-empty-links{justify-content:center;gap:24px}
</style>
