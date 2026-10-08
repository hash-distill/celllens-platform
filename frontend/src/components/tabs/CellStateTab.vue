<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRunStore } from '../../stores/run'
import BlockState, { type BlockDisplay } from '../BlockState.vue'
import ProjectionScatter from '../../charts/ProjectionScatter.vue'
import { CHART_COLORS } from '../../charts/useEChart'
import type { PointSource } from '../../types/run'

/**
 * 细胞状态：二维随机投影散点。
 * 404 时显示「本次结果未提供二维投影」，其他标签页继续可用。
 * online 无 observed 时不补第三组点；实际点数以接口返回为准，不用 n_cells 推算。
 */

const props = defineProps<{ runId: string }>()

const runs = useRunStore()
const entry = computed(() => runs.entry(props.runId))
const block = computed(() => entry.value?.projection ?? null)

const enabledSources = ref<PointSource[]>(['control', 'predicted', 'observed'])
const layout = ref<'compare' | 'overlay'>('compare')
const synthetic = computed(() => entry.value?.record?.request.mode === 'precomputed' || props.runId.startsWith('mock_'))
const sourceLabels = computed<Record<PointSource, string>>(() => ({
  control: synthetic.value ? '合成对照群体' : '对照群体', predicted: synthetic.value ? '合成扰动后群体' : '扰动后预测群体', observed: synthetic.value ? '合成样例观测群体' : '扰动后观测群体',
}))

const sourceCounts = computed(() => {
  const counts: Record<PointSource, number> = { control: 0, predicted: 0, observed: 0 }
  for (const p of block.value?.data?.points ?? []) counts[p.source] += 1
  return counts
})

const presentSources = computed<PointSource[]>(() =>
  (['control', 'predicted', 'observed'] as PointSource[]).filter((s) => sourceCounts.value[s] > 0),
)

const visibleSources = computed<PointSource[]>(() =>
  presentSources.value.filter((s) => enabledSources.value.includes(s)),
)

const displayedCount = computed(() =>
  visibleSources.value.reduce((sum, s) => sum + sourceCounts.value[s], 0),
)

const SOURCE_META: Record<PointSource, { label: string; color: string; shape: string }> = {
  control: { label: '对照 control', color: CHART_COLORS.control, shape: '●' },
  predicted: { label: '预测 predicted', color: CHART_COLORS.predicted, shape: '●' },
  observed: { label: '观测 observed', color: CHART_COLORS.observed, shape: '▲' },
}

const display = computed<BlockDisplay>(() => {
  const b = block.value
  if (!b || b.status === 'idle' || b.status === 'loading') return 'loading'
  if (b.status === 'error') {
    // 结果文件缺失 / 运行不存在 → 不可用态；其余 → 请求失败
    if (b.error?.status === 404) return 'unavailable'
    if (b.error?.status === 409) return 'unavailable'
    return 'error'
  }
  return (b.data?.points.length ?? 0) > 0 ? 'ok' : 'empty'
})

function toggleSource(source: PointSource): void {
  if (enabledSources.value.includes(source)) {
    if (visibleSources.value.length > 1) {
      enabledSources.value = enabledSources.value.filter((s) => s !== source)
    }
  } else {
    enabledSources.value = [...enabledSources.value, source]
  }
}

function retry(): void {
  runs.retryBlock(props.runId, 'projection')
}
</script>

<template>
  <BlockState
    :display="display"
    :error="block?.error"
    loading-text="正在加载二维投影…"
    empty-text="本次结果没有可显示的投影点"
    unavailable-text="本次结果未提供二维投影"
    unavailable-hint="基因响应与代谢功能标签页仍可正常使用。"
    @retry="retry"
  >
    <div class="legend-row" aria-label="来源图例与开关">
      <button
        v-for="source in presentSources"
        :key="source"
        type="button"
        class="legend-toggle"
        :class="{ off: !enabledSources.includes(source) }"
        :aria-pressed="enabledSources.includes(source)"
        :title="`点击${enabledSources.includes(source) ? '隐藏' : '显示'}${SOURCE_META[source].label}`"
        @click="toggleSource(source)"
      >
        <span class="legend-shape" :style="{ color: SOURCE_META[source].color }" aria-hidden="true">
          {{ SOURCE_META[source].shape }}
        </span>
        {{ sourceLabels[source] }}
        <span class="muted">（{{ sourceCounts[source] }}）</span>
      </button>
      <span class="legend-count">
        当前显示 {{ displayedCount }} 点（上限由后端控制，最多 12000）
      </span>
    </div>

    <div class="state-controls" aria-label="状态分布比较方式">
      <button type="button" class="btn btn-sm" :aria-pressed="layout === 'compare'" @click="layout = 'compare'">并排比较</button>
      <button type="button" class="btn btn-sm" :aria-pressed="layout === 'overlay'" @click="layout = 'overlay'">叠加比较</button>
      <span>共享坐标范围 · 每点一个细胞 · 不逐点配对</span>
    </div>
    <p v-if="synthetic" class="notice notice-warn">当前为合成样例，散点来自合成单细胞表达矩阵，不是 STATE 预测或真实实验观测，不能用于实验验证。{{ block?.data?.original_manifest_sha256 ? '该历史演示的单细胞样例与投影为后续补充，原始结果保留。' : '' }}</p>
    <p v-else-if="block?.data?.population_selection?.status !== 'matched'" class="notice notice-warn">旧分析未记录扰动细胞筛选协议，预测群体可能混有模拟对照；表达与代谢汇总也可能受影响，请新建运行核验。</p>
    <p v-else class="muted small">预测群体已按 {{ block.data.population_selection.perturbation }} 标签筛选：保留 {{ block.data.population_selection.selected_prediction_cells }} 个，排除 {{ block.data.population_selection.excluded_prediction_cells }} 个其他标签细胞。</p>
    <p v-if="!synthetic && sourceCounts.observed === 0" class="muted small">本次运行未提供扰动后观测细胞；当前比较对照与模型预测。</p>
    <div v-if="layout === 'compare'" class="state-comparison">
      <section v-for="source in visibleSources" :key="source" class="state-population" :aria-label="sourceLabels[source]">
        <h3>{{ sourceLabels[source] }} <small>{{ sourceCounts[source] }} 个显示点</small></h3>
        <ProjectionScatter :dark="true" :compact="true" :points="block?.data?.points ?? []" :visible-sources="[source]" :source-labels="sourceLabels" />
      </section>
    </div>
    <ProjectionScatter v-else :dark="true" :points="block?.data?.points ?? []" :visible-sources="visibleSources" :source-labels="sourceLabels" />

    <p class="muted small note">
      方法：{{ block?.data?.method ?? 'seeded-random-projection' }}（种子 {{ block?.data?.seed ?? '—' }}）。
      各来源共用后端投影与坐标范围，页面不做二次降维。这是表达矩阵的可视化，不能称为 STATE 的 SE 嵌入、UMAP 或真实细胞位置；多次运行不能直接叠加。
      细胞序号（cell_index）只在同一来源内有效，相同序号不表示同一个细胞的前后实测轨迹。二维图不能单独证明预测准确性或完整保留高维差异。
    </p>
  </BlockState>
</template>

<style scoped>
.state-controls{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:16px 0}.state-controls button[aria-pressed="true"]{border-color:var(--primary);color:var(--primary);background:#eaf1ea}.state-controls span{font-size:10px;color:var(--muted);margin-left:auto}.state-comparison{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr));gap:14px}.state-population{min-width:0}.state-population h3{font-size:12px;font-weight:500;margin:10px 0}.state-population h3 small{font-size:10px;color:var(--muted);margin-left:8px}.note{line-height:1.8}
.legend-row {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.legend-toggle {
  appearance: none;
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 999px;
  padding: 3px 12px;
  font-size: 12px;
  font-family: var(--font);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ink);
}
.legend-toggle:hover {
  border-color: var(--faint);
}
.legend-toggle.off {
  opacity: 0.45;
}
.legend-shape {
  font-size: 11px;
  line-height: 1;
}
.legend-count {
  margin-left: auto;
  font-size: 12px;
  color: var(--muted);
}
.note {
  margin: 6px 0 0;
}
</style>
