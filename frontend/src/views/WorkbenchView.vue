<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ParamPanel from '../components/ParamPanel.vue'
import StageProgress from '../components/StageProgress.vue'
import EvidenceSidebar from '../components/EvidenceSidebar.vue'
import RunResultOverview from '../components/RunResultOverview.vue'
import ResearchEvidence from '../components/ResearchEvidence.vue'
import UiIcon from '../components/UiIcon.vue'
import MetabolismWorkspace from '../components/function/MetabolismWorkspace.vue'
import CellStateTab from '../components/tabs/CellStateTab.vue'
import GenesTab from '../components/tabs/GenesTab.vue'
import ValidationTab from '../components/tabs/ValidationTab.vue'
import MeasuredComparisonTab from '../components/tabs/MeasuredComparisonTab.vue'
import { useRunStore } from '../stores/run'
import { accessSession } from '../stores/access'
import { useRecentStore } from '../stores/recent'
import { useCandidatesStore } from '../stores/candidates'
import { useDraftStore } from '../stores/draft'
import { useUiStore } from '../stores/ui'
import { api } from '../api/client'
import { apiFetch } from '../api/http'
import type { CellLine, RunRecord } from '../types/run'
import type { ResearchSelection, ResearchResult } from '../types/research'
import { downloadBlob } from '../utils/csv'
import { isSyntheticResult, runSourceLabel } from '../utils/source'
import { STATUS_LABEL, fmtServerTime } from '../utils/format'
import { useAssistantSource, openAssistant } from '../stores/assistantSource'
const route = useRoute(), router = useRouter()
const props = defineProps<{resultsOnly?: boolean}>()
const runs = useRunStore(), recent = useRecentStore(), candidates = useCandidatesStore()
const draft = useDraftStore(), ui = useUiStore()
const readOnly = computed(() => Boolean(accessSession.value?.read_only))
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
const cancelled = computed(() => record.value?.status === 'failed' && record.value.error_code === 'RUN_CANCELLED')
const cancelling = ref(false), cancelNote = ref(''), cancelError = ref('')
let cancelController: AbortController | undefined
const editing = ref(false), downloading = ref(false), resubmitting = ref(false)
const overviewMatched = ref(false)
const focusedTask = ref('')
const canvasSelection = ref<ResearchSelection>({layer:'expression'})
const originalResearchResult = ref<ResearchResult | null>(null)
const selectionLayers: Record<string, ResearchSelection['layer']> = { overview: 'expression', genes: 'expression', cell: 'expression', metabolism: 'function', comparison: 'expression', validation: 'expression' }
const researchSelection=computed<ResearchSelection>(()=>({gene_id:typeof route.query.gene==='string'?route.query.gene:undefined,task_id:typeof route.query.task==='string'?route.query.task:focusedTask.value||undefined,layer:selectionLayers[activeTab.value] ?? 'expression',...(activeTab.value==='overview'?canvasSelection.value:{})}))
const reportNote = ref('')
const packageKind = ref<'analysis'|'single-cell'|'network'|'ranking'>('analysis')
const packageDownloading = ref(false), packageNote = ref('')
let reportController: AbortController | undefined, packageController: AbortController | undefined
const packageUnavailable = computed(() => !record.value || record.value.status !== 'completed' ? '实验完成后可导出结果包'
  : isSyntheticResult(record.value.request.mode,runId.value,record.value.result_kind) ? '合成数据暂不支持结果包导出'
  : record.value.request.mode === 'validation' || activeTab.value === 'comparison' ? '实测对比请使用下方的完整对比 CSV 或来源 JSON' : '')
const tabs = [{key:'overview',label:'研究总览'},{key:'genes',label:'表达响应'},{key:'metabolism',label:'代谢任务'},{key:'comparison',label:'实验对照'}]
const activeTab = computed(() => readOnly.value ? 'overview' : route.query.tab === 'function' ? 'metabolism' : route.query.tab === 'validation' ? record.value?.request.mode === 'validation' ? 'validation' : 'comparison' : route.query.tab === 'cell' ? 'cell' : tabs.some(tab => tab.key === route.query.tab) ? String(route.query.tab) : 'overview')
useAssistantSource(() => !readOnly.value && record.value ? {
  kind:'run', id:runId.value, title:`${record.value.request.cell_line} · ${record.value.request.perturbation}`,
  completed:record.value.status === 'completed',
  view:activeTab.value === 'genes' ? 'genes' : activeTab.value === 'metabolism' ? 'metabolism' : activeTab.value === 'comparison' || (activeTab.value === 'overview' && overviewMatched.value) ? 'comparison' : 'overview',
} : null)
watch(() => route.query.tab, tab => { if(tab==='function') void router.replace({path:route.path,query:{...route.query,tab:'metabolism',view:'function'}}) }, {immediate:true})
watch(runId, id => { cancelController?.abort();cancelling.value=false;cancelNote.value='';cancelError.value='';focusedTask.value='';originalResearchResult.value=null;canvasSelection.value={layer:'expression'};overviewMatched.value=false;reportController?.abort();packageController?.abort();downloading.value=false;packageDownloading.value=false;packageNote.value='';editing.value=!id; reportNote.value=''; if(id) runs.openRun(id); else runs.leaveRun() }, {immediate:true,flush:'sync'})
watch(activeTab, () => {packageController?.abort();packageDownloading.value=false;packageNote.value=''}, {flush:'sync'})
watch(record, rec => { if(rec) recent.add({run_id:rec.run_id,cell_line:rec.request.cell_line,perturbation:rec.request.perturbation,mode:rec.request.mode,status:rec.status}) }, {immediate:true})
watch([() => record.value?.status, activeTab], ([status,tab]) => {if(status==='completed' && tab!=='overview' && tab!=='cell' && tab!=='comparison') runs.ensureTabData(runId.value,tab)}, {immediate:true})
onBeforeUnmount(() => {cancelController?.abort();reportController?.abort();packageController?.abort();runs.leaveRun()})
function selectTab(tab:string) { void router.replace({path:route.path,query:{...route.query,run:typeof route.params.runId === 'string' ? undefined : runId.value,tab:tab==='overview'?undefined:tab}}) }
function fillDraft() { if(!readOnly.value && record.value) { draft.applyFromRequest(record.value.request); if(props.resultsOnly) void router.push('/research?type=prediction'); else editing.value=true; ui.push('info','已复用本次参数，可调整并提交新实验') } }
function addCandidate() { if(!readOnly.value && record.value) { const result=candidates.add(runId.value,record.value.request); ui.push(result.ok?'success':'warning',result.ok?'已加入比较，可从实验记录中的“预测结果比较”进入':result.reason ?? '无法加入比较') } }
async function downloadReport() { if(readOnly.value || record.value?.status!=='completed' || downloading.value)return; const id=runId.value,current=reportController=new AbortController();downloading.value=true; reportNote.value=''; try {const result=await api.downloadReport(id,current.signal);if(!current.signal.aborted && id===runId.value)downloadBlob(result.blob,result.filename)} catch(error) {if(!current.signal.aborted)reportNote.value=error instanceof Error?error.message:'报告下载失败'} finally {if(!current.signal.aborted)downloading.value=false} }
async function downloadPackage() {
  if (readOnly.value || packageUnavailable.value || packageDownloading.value) return
  const id=runId.value,chosen=packageKind.value,current=packageController=new AbortController()
  packageDownloading.value=true;packageNote.value=''
  try {
    const result=await api.getExportPackage(id,chosen,current.signal)
    if(!current.signal.aborted && id===runId.value) downloadBlob(result.blob,result.filename)
  } catch(error) {if(!current.signal.aborted)packageNote.value=error instanceof Error?error.message:'结果包下载失败'}
  finally {if(!current.signal.aborted)packageDownloading.value=false}
}
async function cancelRun() {
  if(readOnly.value || cancelling.value || !record.value || ['completed','failed'].includes(record.value.status)) return
  const id=runId.value,current=cancelController=new AbortController()
  cancelling.value=true;cancelNote.value='';cancelError.value=''
  try {
    const updated=await apiFetch<RunRecord>(`/runs/${encodeURIComponent(id)}/cancel`,{method:'POST',signal:current.signal})
    if(current.signal.aborted || id!==runId.value) return
    if(updated.run_id!==id) throw new Error('取消响应的运行编号不匹配')
    await runs.refreshRecord(id)
    if(current.signal.aborted || id!==runId.value) return
    cancelNote.value=updated.error_code==='RUN_CANCELLED'?'任务已取消。':updated.status==='completed'?'任务已完成，保留已有结果。':'任务已结束，请查看运行状态。'
  } catch(error) {if(!current.signal.aborted)cancelError.value=`${error instanceof Error?error.message:'取消请求失败'}；请刷新运行状态核对。`}
  finally {if(cancelController===current)cancelling.value=false}
}
async function resubmit() { if(readOnly.value || !record.value || resubmitting.value)return;resubmitting.value=true;try {const result=await runs.createRun({...record.value.request, mode:'online'});if(result) await router.push({path:'/workbench',query:{run:result.run_id}});else ui.push('error',runs.submitError?.message ?? '重新提交失败')}finally{resubmitting.value=false} }
</script>
<template>
  <div class="page workbench-page national-page" :class="{'has-run': Boolean(runId)}">
    <header v-if="!props.resultsOnly && !readOnly" class="page-heading"><div><span class="eyebrow">MODEL PREDICTION WORKBENCH</span><h1>模型预测工作台</h1><p>明确运行模型预测，分析生成的扰动表达，并与可用实测进行比较。</p></div><div class="btn-row"><RouterLink to="/measured" class="btn">实测分析</RouterLink><RouterLink to="/records?category=predicted" class="btn">预测记录</RouterLink><RouterLink v-if="runId" to="/workbench" class="btn btn-primary">新建预测</RouterLink></div></header>
    <details v-if="!props.resultsOnly && !readOnly" class="workspace-configuration" :open="editing" @toggle="editing=($event.target as HTMLDetailsElement).open"><summary><span>{{ runId ? '下一次实验设置' : '实验设置' }}</span><small>{{ runId ? '修改参数不会改变当前结果' : '选择细胞背景、扰动与采样参数' }}</small><span class="configuration-toggle">{{ editing ? '收起' : '展开' }}</span></summary><ParamPanel destination="workbench" horizontal /></details>
    <section v-if="!runId" class="workspace-empty"><span class="eyebrow">EXPLICIT MODEL PREDICTION</span><h2>{{readOnly?'浏览已发布的冻结案例':'按研究问题选择预测。'}}</h2><p>{{readOnly?'公开展览仅提供已登记案例的冻结结果；新建与完整分析在私人工作区中进行。':'预测完成后可分析生成的表达与代谢评分；当前固定源缺少实测，不代表全球未测，也不证明模型已验证泛化。'}}</p><div class="btn-row workspace-empty-links"><RouterLink to="/data-catalog">先查询数据覆盖 →</RouterLink><RouterLink to="/records?status=completed&amp;category=predicted">解读已有预测 →</RouterLink></div></section>
    <section v-else class="workspace-results" aria-label="本次实验分析">
      <nav v-if="props.resultsOnly" class="result-breadcrumb" aria-label="研究路径"><RouterLink to="/">研究概览</RouterLink><span>/</span><RouterLink to="/records?category=predicted">模型研究记录</RouterLink><span>/</span><strong>研究工作台</strong></nav>
      <header class="active-experiment"><div class="experiment-identity"><span class="eyebrow">PERTURBATION EXPLORER · 模型响应</span><component :is="props.resultsOnly ? 'h1' : 'h2'" v-if="record">{{ record.request.cell_line }} <span class="identity-divider">/</span> {{ record.request.perturbation }} <span class="pill pill-neutral">{{ cancelled?'已取消':STATUS_LABEL[record.status] }}</span></component><h2 v-else>读取实验记录</h2><p v-if="record" class="experiment-meta">{{ runSourceLabel(record.request.mode,runId,record.result_kind) }} · {{ record.request.mode === 'precomputed' ? '读取已保存结果' : '请求 '+record.request.n_cells+' 个预测细胞' }} · {{ fmtServerTime(record.created_at) }}</p><p class="run-identity mono">{{ runId }}</p></div>
        <div v-if="!readOnly" class="experiment-actions btn-row"><RouterLink v-if="props.resultsOnly" to="/research" class="btn btn-sm">＋ 新建分析</RouterLink><RouterLink v-if="record?.status==='completed'" :to="`/figures/prediction/${encodeURIComponent(runId)}`" class="btn btn-sm">图表工作区</RouterLink><button v-if="record?.status==='completed'" class="btn btn-sm" :disabled="candidates.has(runId)" @click="addCandidate">{{ candidates.has(runId)?'已加入比较':'加入比较' }}</button><button v-else class="btn btn-sm" @click="runs.refreshRecord(runId)">刷新状态</button><button v-if="record && !['completed','failed'].includes(record.status)" class="btn btn-sm" :disabled="cancelling" @click="cancelRun">{{cancelling?'正在取消…':'取消运行'}}</button>
          <details class="result-action-menu" @keydown.esc="($event.currentTarget as HTMLDetailsElement).open=false"><summary class="btn btn-sm"><UiIcon name="export" :size="14"/> 导出与更多 <span class="menu-chevron" aria-hidden="true">⌄</span></summary><div class="result-action-popover"><span class="action-menu-label">研究操作</span><button v-if="record" class="result-menu-item" @click="fillDraft"><UiIcon name="layers" :size="15"/><span>复用本次参数<small>创建下一次研究，保留当前结果</small></span></button><button class="result-menu-item" @click="runs.refreshRecord(runId)"><UiIcon name="reset" :size="15"/><span>刷新运行状态</span></button><RouterLink to="/records" class="result-menu-item"><UiIcon name="file" :size="15"/><span>查看实验记录</span></RouterLink><template v-if="record?.status==='completed'"><div class="action-menu-divider"/><span class="action-menu-label">结果与研究包</span><button class="result-menu-item" :disabled="downloading" @click="downloadReport"><UiIcon name="export" :size="15"/><span>{{ downloading?'报告下载中…':'导出 PDF 报告' }}</span></button><label class="action-package-label" for="prediction-package-kind">结果包类型</label><div class="package-export"><select id="prediction-package-kind" v-model="packageKind" :disabled="packageDownloading || !!packageUnavailable"><option value="analysis">分析结果包 ZIP</option><option value="single-cell">单细胞分析包 ZIP</option><option value="network">网络包 ZIP</option><option value="ranking">基因排序包 ZIP</option></select><button class="btn btn-sm btn-primary" :disabled="packageDownloading || !!packageUnavailable" :title="packageUnavailable || undefined" @click="downloadPackage">{{ packageDownloading?'下载中…':'下载' }}</button></div><p v-if="packageUnavailable" class="action-menu-note">{{ packageUnavailable }}</p></template></div></details>
        </div>
      </header>
      <p v-if="cancelNote" class="muted" role="status">{{cancelNote}}</p><p v-if="cancelError" class="notice notice-danger" role="alert">{{cancelError}}</p>
      <p v-if="packageNote" class="notice notice-warn" role="alert">{{ packageNote }}</p>
      <div v-if="entry?.notFound" class="card"><h2>运行不存在</h2><p>请检查运行编号，或从实验记录中打开其他实验。</p><RouterLink to="/records" class="btn">查看实验记录</RouterLink></div>
      <div v-else-if="!record" class="card"><p>{{ entry?.recordError ? '运行记录读取失败：'+entry.recordError.message : '正在读取所选实验…' }}</p><button v-if="entry?.recordError" class="btn" @click="runs.refreshRecord(runId)">重试运行记录</button></div>
      <template v-else>
        <p v-if="entry?.recordError" class="notice notice-warn">{{ entry.recordError.message }}</p><p v-if="reportNote" class="notice notice-warn">{{ reportNote }}</p>
        <StageProgress v-if="record.status!=='completed'" :record="record" :poll-issue="entry?.pollIssue" />
        <div v-if="record.status==='failed'" class="card"><h2>{{cancelled?'本次分析已取消':'本次分析失败'}}</h2><p>{{cancelled?'任务已停止，运行参数与取消记录已保留。':record.error_message || '请检查运行来源与错误记录。'}}</p><button v-if="!readOnly" class="btn btn-primary" :disabled="resubmitting" @click="resubmit">{{ resubmitting?'提交中…':'以相同参数重新运行' }}</button></div>
        <template v-if="record.status==='completed'"><ResearchEvidence kind="prediction" :record-id="runId" :selection="researchSelection" completed @loaded="originalResearchResult=$event" /><div v-if="activeTab!=='overview'" class="result-interpretation"><span>结合当前结果，解释图表与数据变化</span><button type="button" class="btn btn-sm" @click="openAssistant(false)">解读当前结果</button></div><div v-if="!readOnly" class="tabs result-tabs" role="tablist" aria-label="分析结果"><button v-for="tab in tabs" :key="tab.key" class="tab" :class="{active:activeTab===tab.key || (tab.key==='genes' && activeTab==='cell') || (tab.key==='comparison' && activeTab==='validation')}" role="tab" :aria-selected="activeTab===tab.key || (tab.key==='genes' && activeTab==='cell') || (tab.key==='comparison' && activeTab==='validation')" @click="selectTab(tab.key)">{{ tab.label }}</button></div><p v-if="['genes','metabolism'].includes(activeTab)" class="muted small">本页为原运行群体；匹配后的可用群体比较见“实验对照”。</p><RunResultOverview v-if="activeTab==='overview'" :key="runId" :run-id="runId" :original-result="originalResearchResult" @comparison-mode="overviewMatched = $event" @focus-task="focusedTask=$event" @selection="canvasSelection=$event" /><MetabolismWorkspace v-else-if="activeTab==='metabolism'" :key="runId" :run-id="runId" /><div v-else class="card analysis-panel"><CellStateTab v-if="activeTab==='cell'" :key="runId" :run-id="runId" /><GenesTab v-else-if="activeTab==='genes'" :run-id="runId" /><MeasuredComparisonTab v-else-if="activeTab==='comparison'" :key="runId" :run-id="runId" /><ValidationTab v-else :run-id="runId" /></div></template>
        <details v-if="entry && !readOnly" class="run-evidence"><summary>实验参数与数据来源</summary><EvidenceSidebar :entry="entry" /></details>
      </template>
    </section>
  </div>
</template>
<style scoped>
.result-interpretation{display:flex;align-items:center;justify-content:flex-end;gap:16px;margin:20px 0 10px;font-size:12px;color:var(--muted)}
.workspace-configuration{border:1px solid var(--border);background:var(--card);margin-bottom:24px}.workspace-configuration>summary{display:flex;align-items:center;gap:16px;padding:18px 24px;cursor:pointer;font-size:13px;color:var(--primary);list-style:none}.workspace-configuration>summary small{font-size:11px;color:var(--muted)}.configuration-toggle{margin-left:auto;font-size:10px}.workspace-configuration :deep(.param-panel>.card){border:0;border-top:1px solid var(--border);margin:0}.workspace-empty{padding:66px 24px;border-top:1px solid var(--border);text-align:center}.workspace-empty h2{font-size:26px;font-weight:500;margin:16px 0}.workspace-empty p{font-size:12px;color:var(--muted);line-height:1.9}.workspace-empty a{font-size:12px;display:inline-block;margin-top:14px}.active-experiment{display:flex;justify-content:space-between;gap:24px;align-items:center;padding:24px;background:var(--card);border:1px solid var(--border);margin-bottom:20px}.active-experiment h1,.active-experiment h2{font-size:22px;font-weight:500;margin:10px 0}.active-experiment .pill{font-size:10px;margin-left:12px;vertical-align:middle}.run-identity{font-size:10px;color:var(--muted);overflow-wrap:anywhere;margin:0}.experiment-meta{font-size:10px;color:var(--muted);line-height:1.9;margin:8px 0 0}.experiment-actions{max-width:430px;justify-content:flex-end}.result-tabs{margin-bottom:20px;overflow-x:auto;flex-wrap:nowrap;white-space:nowrap}.analysis-panel{margin-top:0}.run-evidence{margin-top:20px;border:1px solid var(--border);background:var(--card)}.run-evidence>summary{padding:16px 24px;cursor:pointer;font-size:12px;color:var(--primary)}.run-evidence :deep(.card){border:0;margin:0}
.package-export{display:flex;gap:6px;align-items:center}.package-export select{border:1px solid var(--border);background:var(--card);color:var(--ink);padding:7px;font:11px var(--font);max-width:190px}.package-export select:disabled{opacity:.55}
.workspace-empty-links{justify-content:center;gap:24px}

.result-breadcrumb{display:flex;align-items:center;gap:10px;font-size:10px;color:var(--muted);margin:0 0 20px}.result-breadcrumb a{color:var(--muted);text-decoration:none}.result-breadcrumb strong{font-weight:500;color:var(--primary)}.experiment-identity{min-width:0}.identity-divider{font-weight:300;color:var(--border-strong);margin:0 4px}.active-experiment .run-identity{font-size:9px!important;color:var(--faint);margin-top:8px}.active-experiment .experiment-meta{font-size:11px!important}.active-experiment{align-items:flex-start;border-radius:16px!important;box-shadow:var(--shadow);border-left:1px solid var(--border)!important}.active-experiment .experiment-actions{flex:none;gap:8px;max-width:none;padding-top:4px}.active-experiment h1,.active-experiment h2{font-size:29px!important;font-weight:500!important;margin:10px 0!important}.result-action-menu{position:relative;z-index:21;margin:0;text-align:left}.result-action-menu>summary{cursor:pointer;list-style:none;white-space:nowrap;display:flex;gap:7px}.result-action-menu>summary::-webkit-details-marker{display:none}.menu-chevron{font-size:13px;margin-left:3px}.result-action-menu[open]>summary{background:var(--primary-weak);border-color:var(--primary);color:var(--primary)}.result-action-popover{position:absolute;right:0;top:calc(100% + 8px);width:290px;max-width:calc(100vw - 40px);border:1px solid var(--border);border-radius:13px;background:var(--card);box-shadow:var(--shadow-lg);padding:16px}.action-menu-label{display:block;font-size:10px;color:var(--faint);margin:1px 7px 8px}.result-menu-item{display:flex;align-items:center;gap:10px;width:100%;padding:10px 8px;background:transparent;border:0;border-radius:7px;color:var(--ink);font:12px var(--font);text-decoration:none;cursor:pointer;text-align:left}.result-menu-item:hover{background:var(--table-row-hover)}.result-menu-item>svg{color:var(--primary);flex:none}.result-menu-item small{display:block;font-size:9px;color:var(--muted);margin-top:5px;line-height:1.6}.action-menu-divider{border-top:1px solid var(--border);margin:9px 0 13px}.action-package-label{display:block;font-size:10px;color:var(--muted);margin:10px 8px 8px}.package-export{display:flex;gap:6px}.package-export select{flex:1;min-width:0;max-width:none;padding:8px;border-radius:6px;font-size:10px}.action-menu-note{font-size:10px;line-height:1.8;color:var(--muted);margin:10px 5px 0}.run-evidence{border-radius:13px}.result-tabs{gap:28px!important;border-bottom:1px solid var(--border);background:none;padding:0 2px;margin:20px 0 22px}.result-tabs .tab{position:relative;padding:13px 0!important;border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent;color:var(--muted);font-size:13px!important}.result-tabs .tab.active{background:transparent;color:var(--primary-strong);border-bottom-color:var(--primary);font-weight:500}.result-interpretation{margin:12px 0 2px;font-size:10px}.result-interpretation .btn{font-size:11px!important}
@media(max-width:1100px){.active-experiment{flex-direction:column;gap:15px}.active-experiment .experiment-actions{align-self:flex-start}.result-action-popover{right:auto;left:0}.active-experiment .experiment-meta{font-size:10px!important}.active-experiment h1,.active-experiment h2{font-size:27px!important}}@media(max-width:650px){.result-breadcrumb{margin:0 0 15px;font-size:9px}.active-experiment{padding:20px!important}.active-experiment h1,.active-experiment h2{font-size:24px!important}.active-experiment .pill{font-size:9px!important;margin-left:7px}.active-experiment .experiment-actions{gap:6px;width:100%;flex-wrap:wrap;justify-content:flex-start}.experiment-actions .btn{font-size:10px!important;padding:8px 10px!important}.result-action-popover{left:auto;right:0}.result-tabs{gap:22px!important}.result-tabs .tab{font-size:12px!important}.result-interpretation>span{display:none}.workspace-configuration>summary{gap:8px;padding:15px}.workspace-configuration>summary small{font-size:10px}.workspace-empty{padding:35px 18px}.workspace-empty h2{font-size:22px}}
.workbench-page :deep(.result-overview){border-radius:15px}.workbench-page :deep(.overview-heading h2){display:none}.workbench-page :deep(.overview-heading){padding:20px 24px 16px}.workbench-page :deep(.overview-heading .eyebrow){font-size:12px;margin-bottom:7px;color:var(--ink);font-weight:500}.workbench-page :deep(.overview-subtitle){font-size:11px;margin-top:0}.workbench-page :deep(.projection-inspection){border-radius:13px;overflow:hidden}
</style>
