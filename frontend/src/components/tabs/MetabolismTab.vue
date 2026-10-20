<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRunStore } from '../../stores/run'
import BlockState, { type BlockDisplay } from '../BlockState.vue'
import DivergingBar, { type DivergingBarItem } from '../../charts/DivergingBar.vue'
import { EVIDENCE_LABEL, fmtDelta, fmtNumber } from '../../utils/format'
import type { EvidenceLevel, EvidenceItem } from '../../types/run'
import TablePager from '../TablePager.vue'
import { usePagedRows } from '../../utils/pagination'
import TaskTrace from '../response/TaskTrace.vue'
import { useTaskAssociations } from '../../utils/taskAssociations'
import { hasPredictionChange } from '../../utils/predictionEvidence'

/**
 * 代谢功能：任务差异图与表格 + 反应聚合表；覆盖详情在独立目录。
 * 优先读取完整有效任务，旧产物明确降级为 Top 摘要；
 * 旧运行的宽表反应文件（INVALID_ARTIFACT）降级为不可用提示。
 */

const props = defineProps<{ runId: string }>()

const runs = useRunStore()
const entry = computed(() => runs.entry(props.runId))
const tasksBlock = computed(() => entry.value?.tasks ?? null)
const reactionsBlock = computed(() => entry.value?.reactions ?? null)

const hasOfficial = computed(() => tasksBlock.value?.data?.completeness_available === true)
function coverageLabel(task: EvidenceItem) {
  return task.coverage >= 1 ? '关联基因齐全' : '存在缺失关联基因'
}

// ---------- 任务 ----------
const allTasks = computed<EvidenceItem[]>(() => (tasksBlock.value?.data?.items ?? []).filter(hasPredictionChange))

const levelCounts = computed(() => {
  const counts: Record<EvidenceLevel, number> = { supported: 0, exploratory: 0, insufficient: 0 }
  for (const task of allTasks.value) counts[task.evidence_level] += 1
  return counts
})

type TaskFilter = 'all' | EvidenceLevel
const evidenceFilter = ref<TaskFilter>('all')
const filterLevels: TaskFilter[] = ['all', 'supported', 'exploratory', 'insufficient']
const filterLabel = (level: TaskFilter) => level === 'all' ? '全部' : EVIDENCE_LABEL[level]
const visibleTasks = computed(() => allTasks.value.filter(
  (t) => hasOfficial.value || evidenceFilter.value === 'all' || t.evidence_level === evidenceFilter.value,
))
const selectedTaskId = ref('')

const taskSearch = ref('')
const searchedTasks = computed(() => {
  const query = taskSearch.value.trim().toLowerCase()
  if (!query) return visibleTasks.value
  return visibleTasks.value.filter(
    (t) =>
      t.label.toLowerCase().includes(query) ||
      t.id.toLowerCase().includes(query),
  )
})

const barItems = computed<DivergingBarItem[]>(() =>
  [...searchedTasks.value]
    .sort((a, b) => Math.abs(b.predicted_delta) - Math.abs(a.predicted_delta))
    .slice(0, 15)
    .map((t) => ({
      id: t.id,
      name: t.label,
      value: t.predicted_delta,
      extra: coverageLabel(t),
    })),
)

const { page: taskPage, pageSize: taskPageSize, pages: taskPages, visible: taskRows } = usePagedRows(searchedTasks)
const { associations, retry: retryAssociations } = useTaskAssociations(() => props.runId, taskRows)
const hasObservedTasks = computed(() => allTasks.value.some(task => task.observed_delta !== null))
const selectedTask = computed(() => searchedTasks.value.find(task => task.id === selectedTaskId.value))
watch(searchedTasks, rows => {
  if (!rows.some(task => task.id === selectedTaskId.value)) selectedTaskId.value = ''
})
watch(() => props.runId, () => {
  evidenceFilter.value = 'all'; taskSearch.value = ''; selectedTaskId.value = ''
})

const tasksDisplay = computed<BlockDisplay>(() => {
  const b = tasksBlock.value
  if (!b || b.status === 'idle' || b.status === 'loading') return 'loading'
  if (b.status === 'error') return b.error?.status === 404 || b.error?.status === 409 ? 'unavailable' : 'error'
  return allTasks.value.length > 0 ? 'ok' : 'empty'
})

const reactionsDisplay = computed<BlockDisplay>(() => {
  if (tasksBlock.value?.data?.reactions_available === false) return 'unavailable'
  const b = reactionsBlock.value
  if (!b || b.status === 'idle' || b.status === 'loading') return 'loading'
  if (b.status === 'error') {
    // 旧运行的细胞×反应宽表结构无法由前端临时聚合，降级为不可用
    if (b.error?.code === 'INVALID_ARTIFACT') return 'unavailable'
    if (b.error?.status === 404 || b.error?.status === 409) return 'unavailable'
    return 'error'
  }
  return (b.data?.items ?? []).some(hasPredictionChange) ? 'ok' : 'empty'
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
  const items = (reactionsBlock.value?.data?.items ?? []).filter(hasPredictionChange)
  const query = reactionSearch.value.trim().toLowerCase()
  const filtered = query
    ? items.filter((r) => r.reaction.toLowerCase().includes(query))
    : [...items]
  const dir = reactionSortDir.value === 'asc' ? 1 : -1
  return filtered.sort((a, b) => ((a.predicted_delta ?? -Infinity) - (b.predicted_delta ?? -Infinity)) * dir)
})
const { page: reactionPage, pageSize: reactionPageSize, pages: reactionPages, visible: reactionRows } = usePagedRows(reactionItems)
</script>

<template>
  <div class="metabolism">
    <p class="muted small">基因和任务的覆盖详情集中在 <RouterLink :to="{path:'/coverage',query:{run:runId}}">查看基因与任务范围 ↗</RouterLink>。部分任务存在缺失关联基因，评分应结合输入范围解读。</p>

    <!-- 任务差异 -->
    <section>
      <div class="flex-between">
        <h3 class="section-title">模型预测的代谢任务变化</h3>
        <span class="pill pill-neutral">{{ tasksBlock?.data?.scope === 'all' ? '全部已生成有效任务结果' : '返回的 Top 摘要' }}（{{ allTasks.length }} 条）</span>
      </div>
      <p class="muted small" style="margin: 0 0 10px">
        任务分数变化不是实测代谢通量。筛选仅覆盖已生成并加载的评分记录，图表取其中绝对变化最大的 15 项。覆盖摘要还可包含未生成分数的任务，未返回不能补零。
        <template v-if="tasksBlock?.data?.scope !== 'all'">当前读取本次运行保存的 Top 摘要，未展示全量任务矩阵。</template>
        <template v-if="tasksBlock?.data?.truncated">服务端已按 limit 截断。</template>
      </p>
      <BlockState
        :display="tasksDisplay"
        :error="tasksBlock?.error"
        loading-text="正在加载代谢任务…"
        empty-text="暂无可展示的代谢任务结果"
        unavailable-text="本次结果未提供代谢任务"
        @retry="runs.retryBlock(props.runId, 'tasks')"
      >
        <div class="filter-row">
          <div v-if="!hasOfficial" class="task-level-filter" role="radiogroup" aria-label="任务覆盖等级筛选">
            <label v-for="level in filterLevels" :key="level" class="filter-check" :class="{active: evidenceFilter === level}">
              <input v-model="evidenceFilter" :name="'task-evidence-'+runId" :value="level" type="radio" />
              <span class="pill" :class="level === 'all' ? 'pill-neutral' : `pill-ev-${level}`">{{ filterLabel(level) }}</span>
              <span class="small muted">（{{ level === 'all' ? allTasks.length : levelCounts[level] }}）</span>
            </label>
          </div>
          <span class="spacer"></span>
          <label class="sr-only" for="task-search">搜索任务</label>
          <input
            id="task-search"
            v-model="taskSearch"
            class="input search-input"
            type="search"
            placeholder="搜索任务名或任务 ID"
          />
        </div>
        <p class="task-filter-status muted small" role="status">当前：{{ filterLabel(evidenceFilter) }} · 匹配 {{ searchedTasks.length }} 项。点击条形或任务名查看详情。</p>

        <template v-if="searchedTasks.length > 0">
          <DivergingBar
            v-if="barItems.length > 0"
            :items="barItems"
            category-name="代谢任务"
            value-label="任务分数变化"
            :height="Math.min(120 + barItems.length * 26, 460)"
            :selected-name="selectedTask?.label"
            @select="selectedTaskId = $event"
          />
          <section v-if="selectedTask" class="task-detail" aria-label="选中代谢任务详情">
            <h4>{{ selectedTask.label }}</h4>
            <p class="muted small">{{ coverageLabel(selectedTask) }} · {{ selectedTask.id }}</p>
            <dl><div><dt>对照分数</dt><dd>{{ fmtNumber(selectedTask.control ?? null) }}</dd></div><div><dt>预测分数</dt><dd>{{ fmtNumber(selectedTask.predicted ?? null) }}</dd></div><div><dt>预测变化</dt><dd>{{ fmtDelta(selectedTask.predicted_delta) }}</dd></div></dl>
          </section>
          <div class="table-wrap" style="margin-top: 12px">
            <table class="table">
              <thead>
                <tr>
                  <th scope="col">任务</th>
                  <th scope="col">预测变化</th>
                  <th v-if="hasObservedTasks" scope="col">观测变化</th>
                  <th scope="col">基因依据</th>
                  <th scope="col">有预测变化的关联基因</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="task in taskRows" :key="task.id" :class="{'selected-task-row': selectedTaskId === task.id}">
                  <td>
                    <button class="task-name-button" :aria-label="'查看任务：'+task.label" :aria-pressed="selectedTaskId === task.id" @click="selectedTaskId = task.id">{{ task.label }}</button>
                    <div class="small faint mono">{{ task.id }}</div>
                  </td>
                  <td>{{ fmtDelta(task.predicted_delta) }}</td>
                  <td v-if="hasObservedTasks">
                    <span :class="{ 'null-value': task.observed_delta === null }">
                      {{ fmtDelta(task.observed_delta) }}
                    </span>
                  </td>
                  <td><RouterLink :to="{path:'/coverage',query:{run:runId,task:task.id}}">{{ coverageLabel(task) }} ↗</RouterLink></td>
                  <td>
                    <template v-if="associations[task.id]?.status === 'ok'">
                      <details v-if="associations[task.id]!.genes.length" class="task-associated-genes"><summary>{{ associations[task.id]!.genes.slice(0,4).join(', ') }}{{ associations[task.id]!.genes.length > 4 ? '…' : '' }} · {{ associations[task.id]!.genes.length }} 个</summary><span class="mono small">{{ associations[task.id]!.genes.join(', ') }}</span></details>
                      <span v-else class="muted small">—</span>
                    </template>
                    <span v-else-if="associations[task.id]?.status === 'loading'" class="muted small">正在读取冻结关联…</span>
                    <span v-else-if="associations[task.id]?.status === 'unavailable'" class="muted small">—</span>
                    <button v-else class="btn btn-sm" :title="associations[task.id]?.error" @click="retryAssociations">关联读取失败 · 重试</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <TablePager v-model:page="taskPage" v-model:page-size="taskPageSize" :pages="taskPages" :total="searchedTasks.length" />
        </template>
        <div v-else class="task-empty notice notice-info" role="status" style="margin-top: 10px">
          当前已加载的{{ tasksBlock?.data?.scope === 'all' ? '任务结果' : ' Top 摘要' }}中没有{{ evidenceFilter === 'all' ? '' : '「'+filterLabel(evidenceFilter)+'」' }}{{ taskSearch.trim() ? '匹配「'+taskSearch.trim()+'」的' : '' }}任务。切换「全部」或清空搜索可查看其他已加载任务。
          <span v-if="tasksBlock?.data?.scope !== 'all'">摘要未包含该等级，不代表全量任务中没有该等级。</span>
        </div>
        <TaskTrace v-if="selectedTask" :run-id="runId" :task-id="selectedTask.id" :task-label="selectedTask.label" :available="selectedTask.trace_available" />
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
        :error="reactionsDisplay === 'unavailable' ? null : reactionsBlock?.error"
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
        <TablePager v-model:page="reactionPage" v-model:page-size="reactionPageSize" :pages="reactionPages" :total="reactionItems.length" />
      </BlockState>
    </section>
  </div>
</template>

<style scoped>
.task-associated-genes{min-width:180px;max-width:330px;white-space:normal;line-height:1.8}.task-associated-genes summary{cursor:pointer;color:var(--primary)}.task-associated-genes>span{display:block;margin-top:8px;overflow-wrap:anywhere}
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
.task-level-filter { display: flex; flex-wrap: wrap; gap: 12px; }
.filter-check { padding: 5px 7px; border: 1px solid transparent; border-radius: 5px; }
.filter-check.active { border-color: var(--border-strong); background: #edf3ec; }
.task-filter-status { margin: 0 0 12px; }
.task-detail { padding: 16px; margin: 14px 0; border: 1px solid var(--border-strong); background: #f5f8f3; }
.task-detail h4 { margin: 0 0 8px; font-size: 14px; }
.task-detail dl { display: flex; flex-wrap: wrap; gap: 28px; }
.task-detail dt { color: var(--muted); font-size: 11px; }
.task-detail dd { margin: 5px 0 0; font-variant-numeric: tabular-nums; }
.task-name-button { border: 0; background: transparent; color: var(--primary); text-align: left; cursor: pointer; font: inherit; padding: 3px 0; text-decoration: underline; text-underline-offset: 3px; }
.selected-task-row { background: #edf3ec; }
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
