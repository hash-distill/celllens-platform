<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { EChartsOption } from 'echarts'
import { useEChart, CHART_COLORS } from './useEChart'

/**
 * 通用「以零为中心发散」水平条形图。
 * 上升为橙红系，下降为蓝紫系，正负方向在坐标与标签中明确。
 */

export interface DivergingBarItem {
  name: string
  value: number
  extra?: string
}

const props = defineProps<{
  items: DivergingBarItem[]
  /** 纵轴标题（如「基因」「代谢任务」） */
  categoryName: string
  /** 数值含义说明，显示在图表上方 */
  valueLabel: string
  height?: number
  selectedName?: string | null
}>()
const emit = defineEmits<{ select: [name: string] }>()

const el = ref<HTMLElement | null>(null)

function buildOption(): EChartsOption {
  // 从小到大排列，最大值显示在最上方
  const sorted = [...props.items].sort((a, b) => a.value - b.value)
  const maxAbs = Math.max(1e-9, ...sorted.map((i) => Math.abs(i.value)))
  const hasSelection = sorted.some(i => i.name === props.selectedName)
  return {
    grid: { left: 8, right: 60, top: 30, bottom: 28, containLabel: true },
    xAxis: {
      type: 'value',
      min: -maxAbs * 1.08,
      max: maxAbs * 1.08,
      name: '← 下降　|　上升 →',
      nameLocation: 'middle',
      nameGap: 24,
      nameTextStyle: { color: '#64748b', fontSize: 12 },
      axisLabel: { color: '#64748b' },
      splitLine: { lineStyle: { color: '#eef2f7' } },
      axisLine: { show: false },
    },
    yAxis: {
      type: 'category',
      data: sorted.map((i) => i.name),
      name: props.categoryName,
      nameTextStyle: { color: '#64748b', fontSize: 12 },
      axisLabel: {
        color: '#172033',
        width: 130,
        overflow: 'truncate',
      },
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      axisTick: { show: false },
    },
    series: [
      {
        type: 'bar',
        data: sorted.map((i) => ({
          value: i.value,
          extra: i.extra,
          itemStyle: { color: i.value >= 0 ? CHART_COLORS.deltaUp : CHART_COLORS.deltaDown, opacity: hasSelection && props.selectedName !== i.name ? 0.35 : 1 },
        })),
        barMaxWidth: 16,
        markLine: {
          symbol: 'none',
          silent: true,
          lineStyle: { color: '#94a3b8', type: 'solid', width: 1 },
          label: { show: false },
          data: [{ xAxis: 0 }],
        },
      },
    ],
    tooltip: {
      trigger: 'item',
      formatter(params) {
        const p = params as unknown as { name: string; value: number; data: { extra?: string } }
        const direction = p.value >= 0 ? '上升' : '下降'
        const lines = [
          `${props.categoryName}：${p.name}`,
          `${props.valueLabel}：${p.value.toFixed(5)}（${direction}）`,
        ]
        if (p.data.extra) lines.push(p.data.extra)
        return lines.join('<br/>')
      },
    },
  }
}

const { getChart } = useEChart(el, buildOption, [() => props.items, () => props.selectedName])
onMounted(() => {
  getChart()?.on('click', params => { if (typeof params.name === 'string') emit('select', params.name) })
})
</script>

<template>
  <div
    ref="el"
    :style="{ width: '100%', height: `${height ?? 360}px` }"
    role="img"
    :aria-label="`${categoryName}差异条形图`"
  ></div>
</template>
