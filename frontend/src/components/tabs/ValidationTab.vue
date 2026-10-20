<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRunStore } from '../../stores/run'
import BlockState, { type BlockDisplay } from '../BlockState.vue'
import ValidationScatter, { type ValidationPair } from '../../charts/ValidationScatter.vue'
import { fmtDelta, fmtNumber } from '../../utils/format'
import { isSyntheticResult } from '../../utils/source'

/**
 * 预测验证：成对 delta 散点 + y=x 参考线；基因与任务分开查看。
 * 不在浏览器计算 Spearman / MAE / 方向一致率 / Top-k 重合率；
 * 指标读取后端已有产物，实验协议状态单独提示。
 */

const props = defineProps<{ runId: string }>()

const runs = useRunStore()
const entry = computed(() => runs.entry(props.runId))
const record = computed(() => entry.value?.record ?? null)
const genesBlock = computed(() => entry.value?.genes ?? null)
const tasksBlock = computed(() => entry.value?.tasks ?? null)
const validationBlock = computed(() => entry.value?.validation ?? null)
const metricLabels: Record<string, string> = {
  spearman:'Spearman', mae:'MAE', direction_agreement:'方向一致率', top_k_overlap:'Top-k 重合率',
  valid_task_count:'有效任务数', excluded_task_count:'排除任务数',
}
const expressionLabels: Record<string, string> = {
  gene_count:'评价基因数', signed_delta_pearson:'有符号变化 Pearson',
  absolute_delta_pearson:'变化幅度 Pearson', mse:'预测变化 MSE',
  no_change_mse:'不变化基线 MSE', mse_relative_to_no_change:'预测 MSE / 基线 MSE',
  direction_agreement:'全基因方向一致率（描述性）',
}
const deLabels: Record<string, string> = {
  observed_significant_genes:'实测显著 DEG 数', predicted_significant_genes:'预测显著 DEG 数',
  overlap_at_n:'DE Overlap@N', overlap_at_50:'DE Overlap@50',
  direction_agreement_on_shared_degs:'共有显著 DEG 方向一致率', average_precision:'DE 平均精确率 AP',
}
function metricValue(value: number | string | boolean | null | undefined): string {
  return fmtNumber(typeof value === 'number' ? value : null)
}

const isOnline = computed(() => record.value?.request.mode === 'online')
const isPrecomputed = computed(() => isSyntheticResult(record.value?.request.mode, props.runId, record.value?.result_kind))

const view = ref<'genes' | 'tasks'>('genes')

interface PairRow extends ValidationPair {
  diff: number
}

const genePairs = computed<PairRow[]>(() =>
  (genesBlock.value?.data?.items ?? [])
    .filter((row) => row.predicted_delta !== null && row.observed_delta !== null)
    .map((row) => ({
      name: row.gene,
      predicted: row.predicted_delta ?? 0,
      observed: row.observed_delta ?? 0,
      diff: Math.abs((row.observed_delta ?? 0) - (row.predicted_delta ?? 0)),
    })),
)

const taskPairs = computed<PairRow[]>(() =>
  (tasksBlock.value?.data?.items ?? [])
    .filter((t) => t.observed_delta !== null)
    .map((t) => ({
      name: t.label,
      predicted: t.predicted_delta,
      observed: t.observed_delta ?? 0,
      diff: Math.abs((t.observed_delta ?? 0) - t.predicted_delta),
    })),
)

const pairs = computed<PairRow[]>(() => (view.value === 'genes' ? genePairs.value : taskPairs.value))

const loadedTotal = computed(() =>
  view.value === 'genes'
    ? (genesBlock.value?.data?.items.length ?? 0)
    : (tasksBlock.value?.data?.items.length ?? 0),
)

const deviationList = computed(() => [...pairs.value].sort((a, b) => b.diff - a.diff).slice(0, 10))

const block = computed(() => (view.value === 'genes' ? genesBlock.value : tasksBlock.value))

const display = computed<BlockDisplay>(() => {
  const b = block.value
  if (!b || b.status === 'idle' || b.status === 'loading') return 'loading'
  if (b.status === 'error') return b.error?.status === 404 || b.error?.status === 409 ? 'unavailable' : 'error'
  return 'ok'
})

function retry(): void {
  runs.retryBlock(props.runId, view.value === 'genes' ? 'genes' : 'tasks')
}
</script>

<template>
  <div class="validation">
    <!-- online 没有匹配观测 -->
    <div v-if="isOnline" class="notice notice-info">
      本次为在线预测，未关联匹配观测。可选择“实测对照”或打开含匹配观测的已完成实验查看比较结果。
    </div>
    <div v-else-if="isPrecomputed" class="notice notice-warn">
      <span class="pill pill-synthetic">合成参考值</span>
      此历史记录的观测数据为合成数据，不能用于实测比较。
    </div>

    <!-- 指标卡：禁止前端计算指标 -->
    <section class="card" style="box-shadow: none">
      <div class="flex-between">
        <h3 class="section-title" style="margin-bottom: 0">代谢任务验证</h3>
        <span class="pill pill-neutral">{{ validationBlock?.data ? '匹配观测分析已完成' : '本次运行未提供指标' }}</span>
      </div>
      <dl v-if="validationBlock?.data" class="evidence-list" style="margin-top: 10px">
        <template v-for="(label, key) in metricLabels" :key="key">
          <dt>{{ label }}</dt><dd>{{ fmtNumber(validationBlock.data.metrics[key] ?? null) }}</dd>
        </template>
      </dl>
      <p class="muted small" style="margin: 8px 0 0">
        指标基于本次运行完整任务中的有效成对变化计算。当前观测的训练排除关系未核实，数值用于匹配观测比较，不作为独立留出泛化评价。
      </p>
      <p v-if="validationBlock?.status === 'error' && validationBlock.error?.status !== 404" class="notice notice-warn">
        指标读取失败：{{ validationBlock.error?.message }}
        <button class="btn btn-sm" @click="runs.retryBlock(props.runId, 'validation')">重试指标</button>
      </p>
    </section>

    <section class="card" aria-label="STATE 表达预测验证" style="box-shadow: none">
      <h3 class="section-title">STATE 表达预测验证</h3>
      <template v-if="validationBlock?.data?.expression">
        <dl class="evidence-list">
          <template v-for="(label, key) in expressionLabels" :key="key">
            <dt>{{ label }}</dt><dd>{{ metricValue(validationBlock.data.expression[key]) }}</dd>
          </template>
        </dl>
        <p class="muted small">在统一 log1p(CP10K) 尺度比较群体变化。MSE 比值小于 1 表示本次误差低于不变化基线。</p>
        <h4>差异表达诊断</h4>
        <dl v-if="validationBlock.data.differential_expression" class="evidence-list">
          <template v-for="(label, key) in deLabels" :key="key">
            <dt>{{ label }}</dt><dd>{{ metricValue(validationBlock.data.differential_expression[key]) }}</dd>
          </template>
        </dl>
        <p class="muted small">Wilcoxon + BH，FDR &lt; 0.05。无显著基因或无法计算时显示缺失；细胞级检验不能替代独立生物学重复。</p>
      </template>
      <p v-else class="muted small">本次运行未提供表达预测验证。代谢任务指标不能代替基因表达准确率。</p>
      <p class="notice notice-warn">评价范围为本次匹配观测。训练排除关系未核实，不能据此推断对未见扰动的泛化能力；细胞级比较也不能替代独立生物学重复。</p>
    </section>

    <!-- 成对散点 -->
    <section>
      <div class="flex-between">
        <h3 class="section-title">预测变化 × 观测变化</h3>
        <div class="view-toggle" role="tablist" aria-label="查看对象">
          <button
            class="btn btn-sm"
            :class="{ 'btn-primary': view === 'genes' }"
            role="tab"
            :aria-selected="view === 'genes'"
            @click="view = 'genes'"
          >
            基因
          </button>
          <button
            class="btn btn-sm"
            :class="{ 'btn-primary': view === 'tasks' }"
            role="tab"
            :aria-selected="view === 'tasks'"
            @click="view = 'tasks'"
          >
            代谢任务
          </button>
        </div>
      </div>

      <BlockState
        :display="display"
        :error="block?.error"
        loading-text="正在加载成对数据…"
        unavailable-text="本次结果未提供可用于验证的记录"
        @retry="retry"
      >
        <template v-if="pairs.length > 0">
          <p class="muted small" style="margin: 0 0 6px">
            只绘制预测变化与观测变化均为有效数值的记录：成对有效值 {{ pairs.length }} / 已加载
            {{ loadedTotal }}。基因与任务分开查看，不混在同一坐标中。
          </p>
          <ValidationScatter :pairs="pairs" :item-name="view === 'genes' ? '基因' : '代谢任务'" />

          <h4 class="deviation-title">偏差最大的项目（描述性列表，按 |观测 − 预测| 排序）</h4>
          <div class="table-wrap">
            <table class="table">
              <thead>
                <tr>
                  <th scope="col">{{ view === 'genes' ? '基因' : '任务' }}</th>
                  <th scope="col">预测变化</th>
                  <th scope="col">观测变化</th>
                  <th scope="col">|观测 − 预测|</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in deviationList" :key="row.name">
                  <td>{{ row.name }}</td>
                  <td>{{ fmtDelta(row.predicted) }}</td>
                  <td>{{ fmtDelta(row.observed) }}</td>
                  <td>{{ row.diff.toFixed(5) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
        <div v-else class="state-empty-box">
          <p class="state-empty-title">没有成对有效值</p>
          <p class="muted small">
            {{ view === 'genes' ? '已加载基因记录中没有同时提供观测变化的条目。' : '已加载任务中没有提供观测变化的条目。' }}
            {{ isOnline ? '在线预测不提供匹配观测。' : '' }}
          </p>
        </div>
      </BlockState>
    </section>
  </div>
</template>

<style scoped>
.validation {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.section-title {
  font-size: 15px;
  margin-bottom: 8px;
}
.view-toggle {
  display: inline-flex;
  gap: 6px;
}
.deviation-title {
  font-size: 13px;
  color: var(--muted);
  margin: 14px 0 8px;
}
.state-empty-box {
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 20px;
  text-align: center;
  background: var(--coverage-bg);
}
.state-empty-title {
  margin: 0 0 4px;
  font-weight: 600;
}
</style>
