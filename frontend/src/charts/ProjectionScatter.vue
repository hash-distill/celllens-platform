<script setup lang="ts">
import { ref } from 'vue'
import type { EChartsOption, SeriesOption } from 'echarts'
import { useEChart, CHART_COLORS } from './useEChart'
import type { PointSource, ProjectionPoint } from '../types/run'
import { SOURCE_LABEL } from '../utils/format'

/**
 * 二维随机投影散点图。
 * 标题固定为「二维随机投影」，轴为「投影轴 1 / 投影轴 2」，
 * 不得命名为 UMAP、t-SNE 或真实细胞空间。
 */
const props = defineProps<{
  points: ProjectionPoint[]
  visibleSources: PointSource[]
  dark?: boolean
}>()

const el = ref<HTMLElement | null>(null)

const SOURCE_META: Record<PointSource, { color: string; symbol: string }> = {
  control: { color: CHART_COLORS.control, symbol: 'circle' },
  predicted: { color: CHART_COLORS.predicted, symbol: 'circle' },
  observed: { color: CHART_COLORS.observed, symbol: 'triangle' },
}

function buildOption(): EChartsOption {
  const textColor = props.dark ? '#a8c0ba' : '#6b7778'
  const lineColor = props.dark ? '#304443' : '#e5e8e0'
  const series: SeriesOption[] = (['control', 'predicted', 'observed'] as PointSource[])
    .filter((source) => props.visibleSources.includes(source))
    .map((source) => {
      const meta = SOURCE_META[source]
      const data = props.points
        .filter((p) => p.source === source)
        .map((p) => ({ value: [p.x, p.y], cellIndex: p.cell_index, source }))
      return {
        name: SOURCE_LABEL[source],
        type: 'scatter',
        symbol: meta.symbol,
        symbolSize: source === 'control' ? 5 : 6,
        data,
        itemStyle: { color: meta.color, opacity: source === 'control' ? 0.55 : 0.75 },
        emphasis: { itemStyle: { opacity: 1 } },
        large: data.length > 3000,
        largeThreshold: 3000,
      } as SeriesOption
    })

  return {
    title: {
      text: '二维随机投影',
      left: 8,
      top: 4,
      textStyle: { fontSize: 14, color: textColor, fontWeight: 500 },
    },
    grid: { left: 56, right: 24, top: 40, bottom: 44 },
    xAxis: {
      name: '投影轴 1',
      nameLocation: 'middle',
      nameGap: 28,
      type: 'value',
      scale: true,
      axisLine: { lineStyle: { color: lineColor } },
      splitLine: { lineStyle: { color: lineColor } },
      axisLabel: { color: textColor },
      nameTextStyle: { color: textColor },
    },
    yAxis: {
      name: '投影轴 2',
      nameLocation: 'middle',
      nameGap: 40,
      type: 'value',
      scale: true,
      axisLine: { lineStyle: { color: lineColor } },
      splitLine: { lineStyle: { color: lineColor } },
      axisLabel: { color: textColor },
      nameTextStyle: { color: textColor },
    },
    series,
    tooltip: {
      trigger: 'item',
      formatter(params) {
        const p = params as unknown as {
          data: { value: [number, number]; cellIndex: number; source: PointSource }
        }
        const d = p.data
        return [
          `来源：${SOURCE_LABEL[d.source]}（${d.source}）`,
          `细胞序号：${d.cellIndex}`,
          `投影轴 1：${d.value[0].toFixed(4)}`,
          `投影轴 2：${d.value[1].toFixed(4)}`,
        ].join('<br/>')
      },
    },
    toolbox: {
      right: 8,
      top: 4,
      feature: {
        dataZoom: { yAxisIndex: 'none', title: { zoom: '框选缩放', back: '缩放复位' } },
        restore: { title: '复位' },
      },
      iconStyle: { borderColor: '#64748b' },
    },
    dataZoom: [{ type: 'inside', xAxisIndex: 0 }, { type: 'inside', yAxisIndex: 0 }],
  }
}

useEChart(el, buildOption, [() => props.points, () => props.visibleSources])
</script>

<template>
  <div ref="el" class="projection-chart" :class="{dark}" role="img" aria-label="二维随机投影散点图"></div>
</template>

<style scoped>
.projection-chart {
  width: 100%;
  height: 440px;
}
.projection-chart.dark{background:#132024;border-radius:4px;padding:12px}
</style>
