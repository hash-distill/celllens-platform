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
        {{ SOURCE_META[source].label }}
        <span class="muted">（{{ sourceCounts[source] }}）</span>
      </button>
      <span class="legend-count">
        当前显示 {{ displayedCount }} 点（上限由后端控制，最多 12000）
      </span>
    </div>

    <ProjectionScatter
      :dark="true"
      :points="block?.data?.points ?? []"
      :visible-sources="visibleSources"
    />

    <p class="muted small note">
      方法：{{ block?.data?.method ?? 'seeded-random-projection' }}（种子 {{ block?.data?.seed ?? '—' }}）。
      三类点共用后端坐标，页面不做二次降维；多次运行之间坐标不保证可比，不能直接叠加。
      细胞序号（cell_index）只在同一来源内有效。
    </p>
  </BlockState>
</template>

<style scoped>
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
