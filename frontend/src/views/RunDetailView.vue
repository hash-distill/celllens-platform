<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useRunStore } from '../stores/run'
import { useRecentStore } from '../stores/recent'
import { useCandidatesStore } from '../stores/candidates'
import { useUiStore } from '../stores/ui'
import { useDraftStore } from '../stores/draft'
import { api } from '../api/client'
import { runSourceLabel } from '../utils/source'
import { ApiError } from '../api/http'
import { downloadBlob } from '../utils/csv'
import ParamPanel from '../components/ParamPanel.vue'
import InstrumentRail from '../components/InstrumentRail.vue'
import SceneLayers from '../components/scene/SceneLayers.vue'
import ObjectInspector from '../components/scene/ObjectInspector.vue'
import ExperimentDock from '../components/ExperimentDock.vue'
import UiIcon from '../components/UiIcon.vue'
import StageProgress from '../components/StageProgress.vue'
import EvidenceSidebar from '../components/EvidenceSidebar.vue'
import CandidateTray from '../components/CandidateTray.vue'
import CellStateTab from '../components/tabs/CellStateTab.vue'
import GenesTab from '../components/tabs/GenesTab.vue'
import MetabolismTab from '../components/tabs/MetabolismTab.vue'
import ValidationTab from '../components/tabs/ValidationTab.vue'
import { MODE_LABEL, fmtServerTime } from '../utils/format'

/** 运行详情：按 URL 恢复状态；tab=cell|genes|metabolism|validation */

const route = useRoute()
const router = useRouter()
const runs = useRunStore()
const recent = useRecentStore()
const candidates = useCandidatesStore()
const ui = useUiStore()
const draft = useDraftStore()

const runId = computed(() => String(route.params.runId ?? ''))
const entry = computed(() => runs.entry(runId.value))
const record = computed(() => entry.value?.record ?? null)

const TABS = [
  { key: 'structure', label: '细胞结构' },
  { key: 'cell', label: '表达空间' },
  { key: 'genes', label: '基因响应' },
  { key: 'metabolism', label: '代谢功能' },
  { key: 'validation', label: '预测验证' },
] as const

type TabKey = (typeof TABS)[number]['key']

const activeTab = computed<TabKey>(() => {
  const tab = String(route.query.tab ?? 'structure')
  return (TABS.some((t) => t.key === tab) ? tab : 'structure') as TabKey
})

function selectTab(tab: TabKey): void {
  void router.replace({ path: route.path, query: { ...route.query, tab } })
}

// 打开 / 切换运行：取消旧请求，按 URL 恢复
watch(
  runId,
  (id) => {
    if (!id) return
    runs.openRun(id)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  runs.leaveRun()
})

// 记录到达后登记最近运行（本浏览器记录）
watch(
  record,
  (rec) => {
    if (!rec) return
    recent.add({
      run_id: rec.run_id,
      cell_line: rec.request.cell_line,
      perturbation: rec.request.perturbation,
      mode: rec.request.mode,
      status: rec.status,
    })
  },
  { immediate: true },
)

// 完成后按标签页加载数据
watch(
  [() => record.value?.status, activeTab],
  ([status, tab]) => {
    if (status === 'completed') runs.ensureTabData(runId.value, tab === 'structure' ? 'cell' : tab)
  },
  { immediate: true },
)

// ---------- 运行标题区 ----------
const sourceBadge = computed(() => {
  const mode = record.value?.request.mode
  if (!mode) return null
  const text = runSourceLabel(mode, runId.value)
  return { text, cls: text.includes('合成') ? 'pill-synthetic' : 'pill-info' }
})

// ---------- 报告下载 ----------
const reportDownloading = ref(false)
const reportNote = ref<string | null>(null)

const canDownloadReport = computed(() => record.value?.status === 'completed')

const reportDisabledReason = computed(() => {
  if (!record.value) return '运行记录尚未加载'
  if (record.value.status !== 'completed') return '仅分析完成的运行可以下载报告'
  return null
})

async function downloadReport(): Promise<void> {
  if (!canDownloadReport.value || reportDownloading.value) return
  reportDownloading.value = true
  reportNote.value = null
  try {
    const { blob, filename } = await api.downloadReport(runId.value)
    downloadBlob(blob, filename)
    ui.push('success', 'HTML 报告已下载（内容以后端返回为准）')
  } catch (err) {
    if (err instanceof ApiError) {
      reportNote.value =
        err.status === 404 ? '该运行未提供报告（不影响结果浏览）' : `报告下载失败：${err.message}`
    } else {
      reportNote.value = '报告下载失败：未知错误'
    }
  } finally {
    reportDownloading.value = false
  }
}

// ---------- 候选托盘 ----------
function addCandidate(): void {
  const rec = record.value
  if (!rec) return
  const result = candidates.add(rec.run_id, rec.request)
  if (result.ok) {
    candidates.expanded = true
    ui.push('success', '已加入候选托盘（本浏览器记录，最多 4 个）')
  } else if (result.reason) {
    ui.push('warning', result.reason)
  }
}

// ---------- 失败后重新提交（再次创建任务，失败记录保留） ----------
const resubmitting = ref(false)
async function resubmit(): Promise<void> {
  const rec = record.value
  if (!rec || resubmitting.value) return
  resubmitting.value = true
  try {
    const res = await runs.createRun({ ...rec.request })
    if (res) {
      ui.push('success', res.cache_hit ? '已接收：复用已有结果' : '已接收：任务重新进入队列')
      await router.push({ path: `/runs/${encodeURIComponent(res.run_id)}`, query: { tab: 'cell' } })
    } else {
      ui.push('error', runs.submitError?.message ?? '重新提交失败，参数已保留在左侧表单')
    }
  } finally {
    resubmitting.value = false
  }
}

function fillDraft(): void {
  const rec = record.value
  if (!rec) return
  draft.applyFromRequest(rec.request)
  ui.push('info', '已把本次运行参数填入左侧草稿，可调整后提交下一次实验')
}

const CellViewport = defineAsyncComponent(() => import('../components/scene/CellViewport.vue'))

// ---------- 窄屏证据抽屉 ----------
const drawerOpen = ref(false)
</script>

<template>
  <div class="instrument-page result-workspace">
    <div class="context-bar">
      <div><span class="micro">EXPERIMENT / RESULT</span><h1 v-if="record">{{ record.request.cell_line }}<span class="context-slash">/</span>{{ record.request.perturbation }}</h1><h1 v-else>读取实验记录</h1></div>
      <span v-if="sourceBadge" class="context-note">{{ sourceBadge.text }}</span>
    </div>
    <div v-if="entry?.notFound" class="page"><section class="card not-found"><h1>运行不存在</h1><p class="muted">未找到 {{ runId }}。请检查编号或返回工作台。</p><RouterLink to="/workbench" class="btn btn-primary">返回工作台</RouterLink></section></div>
    <div v-else class="instrument-grid">
      <InstrumentRail />
      <aside class="experiment-panel">
        <div class="next-experiment-note">下一次实验 <span>调整草稿不会改变本次结果</span></div>
        <ParamPanel /><SceneLayers v-if="activeTab === 'structure'" />
        <div v-if="record" class="run-sidebar-context"><h2 class="panel-heading">本次参数</h2><dl class="source-list"><dt>背景</dt><dd>{{ record.request.cell_line }}</dd><dt>扰动</dt><dd>{{ record.request.perturbation }}</dd><dt>样本</dt><dd>{{ record.request.n_cells }}</dd><dt>种子</dt><dd>{{ record.request.seed }}</dd></dl><button class="btn btn-sm" type="button" @click="fillDraft">复用实验参数</button></div>
      </aside>
      <section class="workspace-center center-col">
        <div class="card run-header">
          <div class="flex-between">
            <div class="run-heading"><h1 class="run-title">{{ record ? record.request.cell_line+' / '+record.request.perturbation+' 扰动实验' : '正在读取实验…' }}</h1><div v-if="record" class="run-badges"><span class="pill pill-neutral">{{ MODE_LABEL[record.request.mode] }}</span><span class="micro mono" :title="record.run_id">{{ record.run_id }}</span></div></div>
            <div class="btn-row">
              <button class="btn btn-sm" type="button" @click="drawerOpen = true">来源记录</button>
              <button v-if="record" class="btn btn-sm" type="button" :disabled="candidates.has(record.run_id)" @click="addCandidate">{{ candidates.has(record.run_id) ? '已加入候选' : '加入候选' }}</button>
              <button class="btn btn-sm" type="button" :disabled="!canDownloadReport || reportDownloading" :title="reportDisabledReason ?? '下载本次 HTML 报告'" @click="downloadReport"><UiIcon name="export" :size="13" /> {{ reportDownloading ? '下载中…' : '导出报告' }}</button>
              <RouterLink v-if="record" :to="{path:'/demo',query:{run:runId}}" class="btn btn-sm btn-primary">演示本次实验</RouterLink>
            </div>
          </div>
          <p v-if="record" class="micro" style="margin:12px 0 0">{{ record.request.n_cells }} 个采样细胞 · {{ fmtServerTime(record.created_at) }}</p>
          <p v-if="reportNote" class="notice notice-warn" style="margin:10px 0 0">{{ reportNote }}</p>
        </div>
        <template v-if="record">
          <StageProgress v-if="record.status !== 'completed'" :record="record" :poll-issue="entry?.pollIssue ?? null" />
          <div v-else class="completed-line"><span><i class="dot"></i>计算完成</span><span>结果来源：{{ sourceBadge?.text }} · 生物学验证以验证记录为准</span></div>
          <div v-if="record.status === 'failed'" class="card"><h2 class="card-title">本次分析失败</h2><p class="muted small">{{ record.error_message || '请查看来源记录中的错误与限制。' }}</p><div class="btn-row"><button class="btn btn-primary" :disabled="resubmitting" @click="resubmit">{{ resubmitting ? '提交中…' : '以相同参数重新运行' }}</button><button class="btn" @click="fillDraft">复用参数</button></div></div>
          <div v-else class="result-views">
            <div class="tabs result-tabs" role="tablist" aria-label="结果标签页"><button v-for="tab in TABS" :key="tab.key" class="tab" :class="{active:activeTab===tab.key}" role="tab" :aria-selected="activeTab===tab.key" @click="selectTab(tab.key)">{{ tab.label }}</button></div>
            <div v-if="activeTab === 'structure'" class="structure-result"><CellViewport /><ExperimentDock :run-id="runId" /></div>
            <div v-else class="card results-card">
              <div v-if="record.status !== 'completed'" class="notice notice-info">分析完成后自动加载结果。</div>
              <template v-else><CellStateTab v-if="activeTab==='cell'" :run-id="runId" /><GenesTab v-else-if="activeTab==='genes'" :run-id="runId" /><MetabolismTab v-else-if="activeTab==='metabolism'" :run-id="runId" /><ValidationTab v-else :run-id="runId" /></template>
            </div>
          </div>
        </template>
        <div v-else class="card"><p class="muted">正在读取运行记录…</p><div v-if="entry?.recordError" class="notice notice-danger">{{ entry.recordError.message }}<button class="btn btn-sm" @click="runs.refreshRecord(runId)">重试</button></div></div>
      </section>
      <ObjectInspector v-if="activeTab==='structure'" :run-id="runId" />
      <aside v-else-if="entry" class="evidence-dock"><EvidenceSidebar :entry="entry" /></aside>
    </div>
    <footer class="instrument-status"><span>{{ activeTab === 'structure' ? 'STRUCTURE / SCHEMATIC' : 'DATA / ANALYSIS' }}</span><span>细胞结构为示意，结果以本次运行记录为准</span><span>CellLens</span></footer>
    <template v-if="drawerOpen && entry"><div class="evidence-drawer-mask" @click="drawerOpen=false"></div><div class="evidence-drawer"><div class="flex-between" style="padding:16px"><strong>来源与证据记录</strong><button class="btn btn-sm" @click="drawerOpen=false">关闭</button></div><EvidenceSidebar :entry="entry" /></div></template>
    <CandidateTray />
  </div>
</template>
<style scoped>
.next-experiment-note{padding:12px 18px 0;font-size:10px;color:var(--muted)}.next-experiment-note span{display:block;font-size:9px;margin-top:4px;color:var(--faint)}
.run-sidebar-context{border-top:1px solid var(--border);padding:20px 18px;font-size:11px}.run-sidebar-context h2{font-size:12px;font-weight:500}.source-list{display:grid;grid-template-columns:40px 1fr;gap:10px;font-size:11px;margin:14px 0}.source-list dt{color:var(--muted)}.source-list dd{margin:0}.source-list+.btn{width:100%}
.completed-line{display:flex;gap:20px;justify-content:space-between;font-size:10px;color:var(--muted);padding:0 2px;flex-wrap:wrap}.completed-line>span:first-child{color:var(--primary);display:flex;align-items:center;gap:6px}.completed-line .dot{background:var(--primary);width:5px;height:5px}
.result-tabs{background:var(--card);border:1px solid var(--border);padding:0 12px;margin-bottom:12px}.results-card{padding:16px}.not-found{max-width:640px;margin:40px auto;padding:40px}.evidence-drawer{position:fixed;top:0;right:0;bottom:0;width:min(390px,94vw);background:var(--card);z-index:80;overflow:auto;border-left:1px solid var(--border)}.evidence-drawer-mask{position:fixed;inset:0;background:#17252466;z-index:75}.btn-row>.btn{display:inline-flex;align-items:center;gap:5px}
</style>
