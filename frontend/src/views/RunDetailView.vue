<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
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
  { key: 'cell', label: '细胞状态' },
  { key: 'genes', label: '基因响应' },
  { key: 'metabolism', label: '代谢功能' },
  { key: 'validation', label: '预测验证' },
] as const

type TabKey = (typeof TABS)[number]['key']

const activeTab = computed<TabKey>(() => {
  const tab = String(route.query.tab ?? 'cell')
  return (TABS.some((t) => t.key === tab) ? tab : 'cell') as TabKey
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
    if (status === 'completed') runs.ensureTabData(runId.value, tab)
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

// ---------- 窄屏证据抽屉 ----------
const drawerOpen = ref(false)
</script>

<template>
  <div class="page">
    <p class="notice notice-info narrow-hint">当前屏幕较窄，建议在桌面宽度查看完整图表与证据栏。</p>

    <!-- 运行不存在：独立空态 + 返回入口 -->
    <div v-if="entry?.notFound" class="card not-found" role="alert">
      <h1 class="not-found-title">运行不存在</h1>
      <p class="muted">
        没有找到运行 <span class="mono">{{ runId }}</span
        >。可能是编号有误，或该运行已从服务存储中移除。
      </p>
      <div class="btn-row" style="margin-top: 12px">
        <button class="btn btn-primary" type="button" @click="router.push('/workbench')">
          返回工作台
        </button>
        <button class="btn" type="button" @click="runs.refreshRecord(runId)">重新查询</button>
      </div>
    </div>

    <div v-else class="layout-3col">
      <!-- 左：参数面板（下一次实验草稿） -->
      <aside class="col-sticky">
        <ParamPanel />
      </aside>

      <!-- 中：运行与结果 -->
      <section class="center-col">
        <div class="card">
          <div class="flex-between">
            <div class="run-heading">
              <template v-if="record">
                <h1 class="run-title">
                  {{ record.request.cell_line }} / {{ record.request.perturbation }}
                </h1>
                <div class="run-badges">
                  <span v-if="sourceBadge" class="pill" :class="sourceBadge.cls">{{ sourceBadge.text }}</span>
                  <span class="pill pill-neutral">{{ MODE_LABEL[record.request.mode] }}</span>
                  <span class="pill pill-neutral mono" :title="record.run_id">{{ record.run_id }}</span>
                </div>
                <p class="muted small" style="margin: 6px 0 0">
                  n_cells={{ record.request.n_cells }} · seed={{ record.request.seed }} · 创建
                  {{ fmtServerTime(record.created_at) }}
                </p>
              </template>
              <template v-else>
                <div class="skeleton" style="height: 26px; width: 280px"></div>
                <div class="skeleton" style="height: 16px; width: 380px; margin-top: 8px"></div>
              </template>
            </div>
            <div class="btn-row">
              <button
                class="btn btn-sm evidence-drawer-toggle"
                type="button"
                @click="drawerOpen = true"
              >
                证据栏
              </button>
              <button
                v-if="record"
                class="btn btn-sm"
                type="button"
                :disabled="candidates.has(record.run_id)"
                :title="candidates.has(record.run_id) ? '该运行已在候选托盘中' : '加入底部候选托盘（本机记录）'"
                @click="addCandidate"
              >
                {{ candidates.has(record.run_id) ? '已在候选中' : '加入候选' }}
              </button>
              <button
                class="btn btn-sm"
                type="button"
                :disabled="!canDownloadReport || reportDownloading"
                :title="reportDisabledReason ?? '下载后端生成的 HTML 报告'"
                @click="downloadReport"
              >
                {{ reportDownloading ? '下载中…' : '下载 HTML 报告' }}
              </button>
            </div>
          </div>
          <p v-if="reportNote" class="notice notice-warn" style="margin: 10px 0 0">{{ reportNote }}</p>
          <p v-if="!canDownloadReport && record" class="muted small" style="margin: 8px 0 0">
            {{ reportDisabledReason }}。报告与表格 CSV 导出不同：报告由后端生成，CSV 是前端对已公开表格数据的导出。
          </p>
        </div>

        <template v-if="record">
          <StageProgress :record="record" :poll-issue="entry?.pollIssue ?? null" />

          <!-- 失败：保留参数，可明确重新提交 -->
          <div v-if="record.status === 'failed'" class="card">
            <h2 class="card-title">本次分析失败</h2>
            <p class="muted small" style="margin: 0 0 10px">
              失败记录已保留（编号 {{ record.run_id }}）。「重新运行」是再次提交请求，不是覆盖本次记录。
            </p>
            <div class="btn-row">
              <button class="btn btn-primary" type="button" :disabled="resubmitting" @click="resubmit">
                {{ resubmitting ? '提交中…' : '以相同参数重新提交' }}
              </button>
              <button class="btn" type="button" @click="fillDraft">填入左侧草稿</button>
            </div>
          </div>

          <!-- 结果标签页 -->
          <div v-else class="card results-card">
            <div class="tabs" role="tablist" aria-label="结果标签页">
              <button
                v-for="tab in TABS"
                :key="tab.key"
                class="tab"
                :class="{ active: activeTab === tab.key }"
                role="tab"
                :aria-selected="activeTab === tab.key"
                @click="selectTab(tab.key)"
              >
                {{ tab.label }}
              </button>
            </div>

            <div class="tab-body">
              <div v-if="record.status !== 'completed'" class="notice notice-info">
                任务尚未完成（当前：{{ record.status }}），完成后自动加载结果；请避免提前读取产物。
              </div>
              <template v-else>
                <CellStateTab v-if="activeTab === 'cell'" :run-id="runId" />
                <GenesTab v-else-if="activeTab === 'genes'" :run-id="runId" />
                <MetabolismTab v-else-if="activeTab === 'metabolism'" :run-id="runId" />
                <ValidationTab v-else :run-id="runId" />
              </template>
            </div>
          </div>
        </template>

        <!-- 记录尚未加载且非 404：加载骨架 -->
        <div v-else class="card">
          <div class="skeleton" style="height: 18px; width: 50%"></div>
          <div class="skeleton" style="height: 90px; margin-top: 12px"></div>
          <p class="muted small" style="margin: 10px 0 0">正在读取运行记录…</p>
          <div v-if="entry?.recordError" class="notice notice-danger" style="margin-top: 10px">
            读取失败：{{ entry.recordError.message }}
            <button class="btn btn-sm" style="margin-left: 8px" @click="runs.refreshRecord(runId)">重试</button>
          </div>
        </div>
      </section>

      <!-- 右：证据栏 -->
      <aside v-if="entry" class="col-sticky evidence-aside">
        <EvidenceSidebar :entry="entry" />
      </aside>
    </div>

    <!-- 窄屏证据抽屉 -->
    <template v-if="drawerOpen && entry">
      <div class="evidence-drawer-mask" @click="drawerOpen = false"></div>
      <div class="evidence-drawer">
        <div class="flex-between" style="margin-bottom: 10px">
          <strong>证据栏</strong>
          <button class="btn btn-sm" type="button" @click="drawerOpen = false">关闭</button>
        </div>
        <EvidenceSidebar :entry="entry" />
      </div>
    </template>

    <CandidateTray />
  </div>
</template>

<style scoped>
.run-title {
  font-size: 21px;
}
.run-badges {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.results-card {
  padding-top: 10px;
}
.tab-body {
  padding-top: 16px;
}
.not-found {
  max-width: 640px;
  margin: 40px auto;
  text-align: center;
  padding: 40px;
}
.not-found-title {
  font-size: 20px;
  margin-bottom: 8px;
}
</style>
