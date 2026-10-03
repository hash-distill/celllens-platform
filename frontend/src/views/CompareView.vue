<script setup lang="ts">
import { computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useCandidatesStore } from '../stores/candidates'
import { api } from '../api/client'
import { ApiError } from '../api/http'
import { runSourceLabel } from '../utils/source'
import { EVIDENCE_LABEL, fmtDelta, fmtPercent, MODE_LABEL, shortRunId } from '../utils/format'
import CandidateTray from '../components/CandidateTray.vue'
import type { EvidenceItem, RunRecord, RunSummary } from '../types/run'

/**
 * 候选比较（P1）：本机已加入运行的并排描述性表格。
 * 不输出没有依据的优先级评分；任务不在另一运行 Top 20 标「未返回」，不补 0；
 * 尚未核验版本一致，仅描述性并列；合成与真实运行标注来源，不共用排名。
 */

interface CandidateData {
  record: RunRecord | null
  summary: RunSummary | null
  error: ApiError | null
  loading: boolean
}

const router = useRouter()
const candidates = useCandidatesStore()

const dataMap = reactive<Record<string, CandidateData>>({})

onMounted(() => {
  void loadAll()
})

async function loadAll(): Promise<void> {
  await Promise.all(candidates.items.map((item) => loadOne(item.run_id)))
}

async function loadOne(runId: string): Promise<void> {
  dataMap[runId] = { record: null, summary: null, error: null, loading: true }
  try {
    const [recordResult, summaryResult] = await Promise.allSettled([
      api.getRun(runId),
      api.getSummary(runId),
    ])
    if (recordResult.status === 'fulfilled') {
      dataMap[runId].record = recordResult.value
    } else {
      dataMap[runId].error =
        recordResult.reason instanceof ApiError ? recordResult.reason : null
    }
    if (summaryResult.status === 'fulfilled') {
      dataMap[runId].summary = summaryResult.value
    }
  } finally {
    dataMap[runId].loading = false
  }
}

const items = computed(() => candidates.items)

function taskMapOf(runId: string): Map<string, EvidenceItem> {
  const map = new Map<string, EvidenceItem>()
  for (const task of dataMap[runId]?.summary?.metabolic_tasks ?? []) {
    map.set(task.id || task.label, task)
  }
  return map
}

/** 所有运行 Top 任务的并集（保持首次出现顺序） */
const taskUnion = computed(() => {
  const seen = new Map<string, string>()
  for (const item of items.value) {
    for (const task of dataMap[item.run_id]?.summary?.metabolic_tasks ?? []) {
      const key = task.id || task.label
      if (!seen.has(key)) seen.set(key, task.label)
    }
  }
  return [...seen.entries()].map(([key, label]) => ({ key, label }))
})

function sourceLabel(runId: string): string {
  const mode =
    dataMap[runId]?.record?.request.mode ??
    items.value.find((i) => i.run_id === runId)?.request.mode
  return runSourceLabel(mode, runId)
}
</script>

<template>
  <div class="page">
    <div class="card">
      <div class="flex-between">
        <div>
          <h1 class="page-title">候选比较</h1>
          <p class="muted small" style="margin: 6px 0 0">
            <span class="pill pill-neutral">本浏览器记录</span>
            已加入的运行并排展示（最多 4 个，以 run_id 去重）。
            <strong>尚未核验版本一致，仅描述性并列</strong>：请打开各运行证据栏核对历史模型 / 数据哈希与生成时间，
            不输出实验优先级评分；合成演示与真实运行标注来源，不共用排名。
          </p>
        </div>
        <button class="btn" type="button" @click="router.push('/workbench')">返回工作台</button>
      </div>
    </div>

    <div v-if="items.length === 0" class="card empty-card">
      <p class="empty-title">候选托盘为空</p>
      <p class="muted small">
        打开某个运行详情，点击「加入候选」后回到本页查看并排比较。记录仅保存在本浏览器。
      </p>
      <button class="btn btn-primary" type="button" style="margin-top: 12px" @click="router.push('/workbench')">
        去工作台选择运行
      </button>
    </div>

    <template v-else>
      <!-- 基本信息并排表 -->
      <div class="card">
        <h2 class="card-title">基本信息与覆盖摘要</h2>
        <div class="table-wrap">
          <table class="table compare-table">
            <thead>
              <tr>
                <th scope="col">字段</th>
                <th v-for="item in items" :key="item.run_id" scope="col">
                  <div class="mono">{{ shortRunId(item.run_id) }}</div>
                  <button
                    class="btn btn-ghost btn-sm"
                    type="button"
                    :title="`打开运行 ${item.run_id}`"
                    @click="router.push({ path: `/runs/${encodeURIComponent(item.run_id)}`, query: { tab: 'cell' } })"
                  >
                    打开
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">加载状态</th>
                <td v-for="item in items" :key="item.run_id">
                  <span v-if="dataMap[item.run_id]?.loading" class="muted">加载中…</span>
                  <template v-else-if="dataMap[item.run_id]?.error">
                    <span class="pill pill-danger">
                      {{ dataMap[item.run_id]?.error?.status === 404 ? '运行不存在' : '读取失败' }}
                    </span>
                    <button class="btn btn-ghost btn-sm" type="button" @click="loadOne(item.run_id)">重试</button>
                  </template>
                  <span v-else class="pill pill-ok">已加载</span>
                </td>
              </tr>
              <tr>
                <th scope="row">运行状态</th>
                <td v-for="item in items" :key="item.run_id">
                  {{ dataMap[item.run_id]?.record?.status ?? '—' }}
                </td>
              </tr>
              <tr>
                <th scope="row">细胞背景</th>
                <td v-for="item in items" :key="item.run_id">{{ item.request.cell_line }}</td>
              </tr>
              <tr>
                <th scope="row">扰动</th>
                <td v-for="item in items" :key="item.run_id">{{ item.request.perturbation }}</td>
              </tr>
              <tr>
                <th scope="row">模式</th>
                <td v-for="item in items" :key="item.run_id">{{ MODE_LABEL[item.request.mode] }}</td>
              </tr>
              <tr>
                <th scope="row">来源</th>
                <td v-for="item in items" :key="item.run_id">
                  <span
                    class="pill"
                    :class="item.request.mode === 'precomputed' ? 'pill-synthetic' : 'pill-info'"
                  >
                    {{ sourceLabel(item.run_id) }}
                  </span>
                </td>
              </tr>
              <tr>
                <th scope="row">n_cells / seed</th>
                <td v-for="item in items" :key="item.run_id">
                  {{ item.request.n_cells }} / {{ item.request.seed }}
                </td>
              </tr>
              <tr>
                <th scope="row">对齐基因占参考面板比例</th>
                <td v-for="item in items" :key="item.run_id">
                  {{ fmtPercent(dataMap[item.run_id]?.summary?.coverage?.state_gene_fraction ?? null) }}
                </td>
              </tr>
              <tr>
                <th scope="row">代谢库基因覆盖率</th>
                <td v-for="item in items" :key="item.run_id">
                  {{ fmtPercent(dataMap[item.run_id]?.summary?.coverage?.metabolic_gene_fraction ?? null) }}
                </td>
              </tr>
              <tr>
                <th scope="row">反应所需基因平均覆盖比例</th>
                <td v-for="item in items" :key="item.run_id">
                  {{ fmtPercent(dataMap[item.run_id]?.summary?.coverage?.reaction_fraction ?? null) }}
                </td>
              </tr>
              <tr>
                <th scope="row">任务数（覆盖支持/探索性/证据不足）</th>
                <td v-for="item in items" :key="item.run_id">
                  <template v-if="dataMap[item.run_id]?.summary?.coverage">
                    {{ dataMap[item.run_id]?.summary?.coverage?.supported_tasks }} /
                    {{ dataMap[item.run_id]?.summary?.coverage?.exploratory_tasks }} /
                    {{ dataMap[item.run_id]?.summary?.coverage?.insufficient_tasks }}
                  </template>
                  <span v-else class="null-value muted">未提供</span>
                </td>
              </tr>
              <tr>
                <th scope="row">返回 Top 任务数</th>
                <td v-for="item in items" :key="item.run_id">
                  {{ dataMap[item.run_id]?.summary?.metabolic_tasks.length ?? '—' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 任务差异表 -->
      <div class="card">
        <h2 class="card-title">返回任务差异（Top 摘要并集）</h2>
        <p class="muted small" style="margin: 0 0 10px">
          任务未出现在另一运行的返回 Top 列表时标「未返回」，不补 0，也不表示没有变化。
          各运行返回的只是 Top 摘要，不代表全量任务。
        </p>
        <p v-if="taskUnion.length === 0" class="muted small">暂无可比较的任务（汇总尚未加载或均无任务）。</p>
        <div v-else class="table-wrap">
          <table class="table compare-table">
            <thead>
              <tr>
                <th scope="col">代谢任务</th>
                <th v-for="item in items" :key="item.run_id" scope="col" class="mono">
                  {{ shortRunId(item.run_id) }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="task in taskUnion" :key="task.key">
                <th scope="row" style="white-space: normal">{{ task.label }}</th>
                <td v-for="item in items" :key="item.run_id">
                  <template v-if="taskMapOf(item.run_id).get(task.key)">
                    <div>
                      {{ fmtDelta(taskMapOf(item.run_id).get(task.key)?.predicted_delta ?? null) }}
                    </div>
                    <span
                      class="pill"
                      :class="`pill-ev-${taskMapOf(item.run_id).get(task.key)?.evidence_level ?? 'insufficient'}`"
                    >
                      {{ EVIDENCE_LABEL[taskMapOf(item.run_id).get(task.key)?.evidence_level ?? 'insufficient'] }}
                    </span>
                  </template>
                  <span v-else class="null-value muted">未返回</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <CandidateTray />
  </div>
</template>

<style scoped>
.page-title {
  font-size: 21px;
}
.empty-card {
  text-align: center;
  padding: 40px;
}
.empty-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 6px;
}
.compare-table th[scope='row'] {
  background: #f8fafc;
  color: var(--muted);
  font-weight: 600;
  max-width: 260px;
}
</style>
