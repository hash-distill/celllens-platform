<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRunStore } from '../../stores/run'
import BlockState, { type BlockDisplay } from '../BlockState.vue'
import CoverageCards from '../CoverageCards.vue'
import DivergingBar, { type DivergingBarItem } from '../../charts/DivergingBar.vue'
import { EVIDENCE_LABEL, fmtDelta, fmtNumber, fmtPercent } from '../../utils/format'
import type { EvidenceLevel, EvidenceItem } from '../../types/run'
import TablePager from '../TablePager.vue'
import { usePagedRows } from '../../utils/pagination'

/**
 * 代谢功能：覆盖摘要卡 + Top 任务差异图与表格 + 反应聚合表。
 * 优先读取完整有效任务，旧产物明确降级为 Top 摘要；
 * 旧运行的宽表反应文件（INVALID_ARTIFACT）降级为不可用提示。
 */

const props = defineProps<{ runId: string }>()

const runs = useRunStore()
const entry = computed(() => runs.entry(props.runId))
const summaryBlock = computed(() => entry.value?.summary ?? null)
const tasksBlock = computed(() => entry.value?.tasks ?? null)
const reactionsBlock = computed(() => entry.value?.reactions ?? null)

const coverage = computed(() => summaryBlock.value?.data?.coverage ?? null)

// ---------- 任务 ----------
const allTasks = computed<EvidenceItem[]>(() => tasksBlock.value?.data?.items ?? [])

const levelCounts = computed(() => {
  const counts: Record<EvidenceLevel, number> = { supported: 0, exploratory: 0, insufficient: 0 }
  for (const task of allTasks.value) counts[task.evidence_level] += 1
  return counts
})

/** 默认显示覆盖支持 + 探索性；证据不足可切换 */
const showLevels = ref<Record<EvidenceLevel, boolean>>({
  supported: true,
  exploratory: true,
  insufficient: false,
})

const visibleTasks = computed(() => allTasks.value.filter((t) => showLevels.value[t.evidence_level]))

const taskSearch = ref('')
const searchedTasks = computed(() => {
  const query = taskSearch.value.trim().toLowerCase()
  if (!query) return visibleTasks.value
  return visibleTasks.value.filter(
    (t) =>
      t.label.toLowerCase().includes(query) ||
      t.id.toLowerCase().includes(query) ||
      t.determinant_genes.some((g) => g.toLowerCase().includes(query)),
  )
})

const barItems = computed<DivergingBarItem[]>(() =>
  [...searchedTasks.value]
    .sort((a, b) => Math.abs(b.predicted_delta) - Math.abs(a.predicted_delta))
    .slice(0, 15)
    .map((t) => ({
      name: t.label,
      value: t.predicted_delta,
      extra: `证据等级：${EVIDENCE_LABEL[t.evidence_level]}；覆盖 ${(t.coverage * 100).toFixed(1)}%`,
    })),
)

const { page: taskPage, pages: taskPages, visible: taskRows } = usePagedRows(searchedTasks)

const summaryDisplay = computed<BlockDisplay>(() => {
  const b = summaryBlock.value
  if (!b || b.status === 'idle' || b.status === 'loading') return 'loading'
  if (b.status === 'error') return b.error?.status === 404 || b.error?.status === 409 ? 'unavailable' : 'error'
  return coverage.value ? 'ok' : 'unavailable'
})

const tasksDisplay = computed<BlockDisplay>(() => {
  const b = tasksBlock.value
  if (!b || b.status === 'idle' || b.status === 'loading') return 'loading'
  if (b.status === 'error') return b.error?.status === 404 || b.error?.status === 409 ? 'unavailable' : 'error'
  return allTasks.value.length > 0 ? 'ok' : 'empty'
})

const reactionsDisplay = computed<BlockDisplay>(() => {
  const b = reactionsBlock.value
  if (!b || b.status === 'idle' || b.status === 'loading') return 'loading'
  if (b.status === 'error') {
    // 旧运行的细胞×反应宽表结构无法由前端临时聚合，降级为不可用
    if (b.error?.code === 'INVALID_ARTIFACT') return 'unavailable'
    if (b.error?.status === 404 || b.error?.status === 409) return 'unavailable'
    return 'error'
  }
  return (b.data?.items.length ?? 0) > 0 ? 'ok' : 'empty'
})

const reactionsUnavailableText = computed(() => {
  const err = reactionsBlock.value?.error
  if (err?.code === 'INVALID_ARTIFACT') {
    return '该运行的反应结果为旧版宽表结构，当前页面无法展示'
  }
  return '本次结果未提供反应聚合表'
})
const reactionsUnavailableHint = computed(() => {
  const err = reactionsBlock.value?.error
  if (err?.code === 'INVALID_ARTIFACT') {
    return '请使用新版运行重新生成，或联系后端成员处理；页面不会临时聚合出科学结果。'
  }
  return '任务差异与覆盖摘要仍可正常查看。'
})

// ---------- 反应表 ----------
const reactionSearch = ref('')
const reactionSortDir = ref<'asc' | 'desc'>('desc')
const reactionItems = computed(() => {
  const items = reactionsBlock.value?.data?.items ?? []
  const query = reactionSearch.value.trim().toLowerCase()
  const filtered = query
    ? items.filter((r) => r.reaction.toLowerCase().includes(query))
    : [...items]
  const dir = reactionSortDir.value === 'asc' ? 1 : -1
  return filtered.sort((a, b) => ((a.predicted_delta ?? -Infinity) - (b.predicted_delta ?? -Infinity)) * dir)
})
const { page: reactionPage, pages: reactionPages, visible: reactionRows } = usePagedRows(reactionItems)
</script>

<template>
  <div class="metabolism">
    <!-- 覆盖摘要 -->
    <section>
      <h3 class="section-title">覆盖摘要</h3>
      <BlockState
        :display="summaryDisplay"
        :error="summaryBlock?.error"
        loading-text="正在加载覆盖摘要…"
        unavailable-text="本次结果未提供覆盖摘要"
        unavailable-hint="任务可能未完成，或该运行没有代谢结果。"
        :skeleton-rows="2"
        @retry="runs.retryBlock(props.runId, 'summary')"
      >
        <CoverageCards v-if="coverage" :coverage="coverage" />
        <p class="muted small" style="margin: 8px 0 0">
          代谢库基因覆盖率与反应覆盖比例偏低时，下方任务结论应按证据等级解读；
          证据不足的任务不能作为可靠代谢结论（也不代表没有生物效应）。
        </p>
      </BlockState>
    </section>

    <!-- 任务差异 -->
    <section>
      <div class="flex-between">
        <h3 class="section-title">代谢任务差异（scCellFie 任务分数变化）</h3>
        <span class="pill pill-neutral">{{ tasksBlock?.data?.scope === 'all' ? '全部已生成有效任务结果' : '返回的 Top 摘要' }}（{{ allTasks.length }} 条）</span>
      </div>
      <p class="muted small" style="margin: 0 0 10px">
        任务分数变化不是实测代谢通量。筛选仅覆盖已生成并加载的评分记录，图表取其中绝对变化最大的 15 项。覆盖摘要还可包含未生成分数的任务，未返回不能补零。
        <template v-if="tasksBlock?.data?.scope !== 'all'">该运行缺少全量任务及覆盖产物，当前降级为 Top 摘要。</template>
        <template v-if="tasksBlock?.data?.truncated">服务端已按 limit 截断。</template>
        <template v-if="tasksBlock?.data?.excluded_count">有 {{ tasksBlock.data.excluded_count }} 项预测变化无有效数值，已排除；不能按零变化解释。</template>
      </p>
      <BlockState
        :display="tasksDisplay"
        :error="tasksBlock?.error"
        loading-text="正在加载代谢任务…"
        empty-text="本次结果没有代谢任务记录"
        unavailable-text="本次结果未提供代谢任务"
        @retry="runs.retryBlock(props.runId, 'tasks')"
      >
        <div class="filter-row" aria-label="证据等级筛选">
          <label v-for="level in (['supported', 'exploratory', 'insufficient'] as EvidenceLevel[])" :key="level" class="filter-check">
            <input v-model="showLevels[level]" type="checkbox" />
            <span class="pill" :class="`pill-ev-${level}`">{{ EVIDENCE_LABEL[level] }}</span>
            <span class="small muted">（{{ levelCounts[level] }}）</span>
          </label>
          <span class="spacer"></span>
          <label class="sr-only" for="task-search">搜索任务</label>
          <input
            id="task-search"
            v-model="taskSearch"
            class="input search-input"
            type="search"
            placeholder="搜索任务名或关联基因"
          />
        </div>

        <template v-if="searchedTasks.length > 0">
          <DivergingBar
            v-if="barItems.length > 0"
            :items="barItems"
            category-name="代谢任务"
            value-label="任务分数变化"
            :height="Math.min(120 + barItems.length * 26, 460)"
          />
          <div class="table-wrap" style="margin-top: 12px">
            <table class="table">
              <thead>
                <tr>
                  <th scope="col">任务</th>
                  <th scope="col">预测变化</th>
                  <th scope="col">观测变化</th>
                  <th scope="col">覆盖</th>
                  <th scope="col">证据等级</th>
                  <th scope="col">关联基因</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="task in taskRows" :key="task.id">
                  <td>
                    <div>{{ task.label }}</div>
                    <div class="small faint mono">{{ task.id }}</div>
                  </td>
                  <td>{{ fmtDelta(task.predicted_delta) }}</td>
                  <td>
                    <span :class="{ 'null-value': task.observed_delta === null }">
                      {{ fmtDelta(task.observed_delta) }}
                    </span>
                  </td>
                  <td>{{ fmtPercent(task.coverage, 1) }}</td>
                  <td>
                    <span class="pill" :class="`pill-ev-${task.evidence_level}`">
                      {{ EVIDENCE_LABEL[task.evidence_level] }}
                    </span>
                  </td>
                  <td>
                    <template v-if="task.determinant_genes.length > 0">
                      <span class="mono small">{{ task.determinant_genes.join(', ') }}</span>
                    </template>
                    <span v-else class="null-value">关联基因尚未提供</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <TablePager v-model:page="taskPage" :pages="taskPages" :total="searchedTasks.length" />
        </template>
        <div v-else class="notice notice-info" style="margin-top: 10px">
          已加载任务中没有满足当前等级的项目。
          <template v-if="!showLevels.insufficient && levelCounts.insufficient > 0">
            有 {{ levelCounts.insufficient }} 条证据不足任务被隐藏，可勾选上方「证据不足」查看。
          </template>
        </div>
      </BlockState>
    </section>

    <!-- 反应聚合表 -->
    <section>
      <div class="flex-between">
        <h3 class="section-title">反应聚合表</h3>
        <label class="sr-only" for="reaction-search">搜索反应</label>
        <input
          id="reaction-search"
          v-model="reactionSearch"
          class="input search-input"
          type="search"
          placeholder="搜索反应名称"
        />
      </div>
      <BlockState
        :display="reactionsDisplay"
        :error="reactionsBlock?.error"
        loading-text="正在加载反应聚合…"
        empty-text="本次结果没有反应聚合记录"
        :unavailable-text="reactionsUnavailableText"
        :unavailable-hint="reactionsUnavailableHint"
        @retry="runs.retryBlock(props.runId, 'reactions')"
      >
        <p v-if="reactionsBlock?.data?.truncated" class="notice notice-warn">
          当前为部分结果：按绝对变化返回前 {{ reactionsBlock.data.limit }} 条。
        </p>
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th scope="col">反应</th>
                <th scope="col">对照</th>
                <th scope="col">预测</th>
                <th
                  scope="col"
                  class="sortable"
                  @click="reactionSortDir = reactionSortDir === 'asc' ? 'desc' : 'asc'"
                >
                  预测变化{{ reactionSortDir === 'asc' ? ' ▲' : ' ▼' }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="reactionItems.length === 0">
                <td colspan="4" class="muted" style="text-align: center">
                  已加载记录中没有匹配「{{ reactionSearch }}」的反应
                </td>
              </tr>
              <tr v-for="row in reactionRows" :key="row.reaction">
                <td class="mono">{{ row.reaction }}</td>
                <td><span :class="{ 'null-value': row.control === null }">{{ fmtNumber(row.control) }}</span></td>
                <td><span :class="{ 'null-value': row.predicted === null }">{{ fmtNumber(row.predicted) }}</span></td>
                <td>
                  <span :class="{ 'null-value': row.predicted_delta === null }">
                    {{ fmtDelta(row.predicted_delta) }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <TablePager v-model:page="reactionPage" :pages="reactionPages" :total="reactionItems.length" />
      </BlockState>
    </section>
  </div>
</template>

<style scoped>
.metabolism {
  display: flex;
  flex-direction: column;
  gap: 22px;
}
.section-title {
  font-size: 15px;
  margin-bottom: 8px;
}
.filter-row {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.filter-check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 13px;
}
.spacer {
  flex: 1;
}
.search-input {
  max-width: 240px;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
