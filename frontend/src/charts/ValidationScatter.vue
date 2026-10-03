<script setup lang="ts">
import { ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { useEChart, CHART_COLORS } from './useEChart'

/**
 * 预测验证散点：横轴预测变化，纵轴观测变化，附 y=x 参考线。
 * 只绘制两者均为有效数值的成对记录（由父组件过滤后传入）。
 */

export interface ValidationPair {
  name: string
  predicted: number
  observed: number
}

const props = defineProps<{
  pairs: ValidationPair[]
  itemName: string
}>()

const el = ref<HTMLElement | null>(null)

function buildOption(): EChartsOption {
  const values = props.pairs.flatMap((p) => [p.predicted, p.observed])
  const maxAbs = Math.max(1e-9, ...values.map((v) => Math.abs(v)))
  const bound = maxAbs * 1.12
  return {
    grid: { left: 64, right: 24, top: 30, bottom: 46 },
    xAxis: {
      type: 'value',
      name: '预测变化（predicted_delta）',
      nameLocation: 'middle',
      nameGap: 30,
      nameTextStyle: { color: '#64748b', fontSize: 12 },
      min: -bound,
      max: bound,
      axisLabel: { color: '#64748b' },
      splitLine: { lineStyle: { color: '#eef2f7' } },
      axisLine: { lineStyle: { color: '#cbd5e1' } },
    },
    yAxis: {
      type: 'value',
      name: '观测变化（observed_delta）',
      nameLocation: 'middle',
      nameGap: 46,
      nameTextStyle: { color: '#64748b', fontSize: 12 },
      min: -bound,
      max: bound,
      axisLabel: { color: '#64748b' },
      splitLine: { lineStyle: { color: '#eef2f7' } },
      axisLine: { lineStyle: { color: '#cbd5e1' } },
    },
    series: [
      {
        name: '成对记录',
        type: 'scatter',
        symbolSize: 7,
        itemStyle: { color: CHART_COLORS.predicted, opacity: 0.75 },
        data: props.pairs.map((p) => ({ value: [p.predicted, p.observed], name: p.name })),
        markLine: {
          symbol: 'none',
          silent: true,
          lineStyle: { color: CHART_COLORS.observed, type: 'dashed', width: 1.5 },
          label: { show: true, formatter: 'y = x', position: 'end', color: '#b45309' },
          data: [
            [
              { coord: [-bound, -bound] },
              { coord: [bound, bound] },
            ],
          ],
        },
      },
    ],
    tooltip: {
      trigger: 'item',
      formatter(params) {
        const p = params as unknown as { data: { value: [number, number]; name: string } }
        return [
          `${props.itemName}：${p.data.name}`,
          `预测变化：${p.data.value[0].toFixed(5)}`,
          `观测变化：${p.data.value[1].toFixed(5)}`,
        ].join('<br/>')
      },
    },
  }
}

useEChart(el, buildOption, [() => props.pairs])
</script>

<template>
  <div ref="el" class="validation-chart" role="img" aria-label="预测与观测变化散点图"></div>
</template>

<style scoped>
.validation-chart {
  width: 100%;
  height: 420px;
}
</style>
