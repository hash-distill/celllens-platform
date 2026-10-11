<script setup lang="ts">
import { ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { useEChart } from './useEChart'
import type { UserAnalysisReport } from '../types/userData'
const props = defineProps<{projection: UserAnalysisReport['projection']}>()
const el = ref<HTMLElement | null>(null)
useEChart(el, (): EChartsOption => {
  const groups = [...new Set(props.projection.points.map(point => point.group))]
  return {
    color: ['#247a70','#c47654','#c7a45e','#67869a','#9277a2','#84a16c'],
    grid: {left: 65, right: 30, top: 35, bottom: 50},
    tooltip: {trigger: 'item', renderMode: 'richText', formatter: (params: unknown) => {
      const value = params as {data?: {cellId?: string}; seriesName?: string}
      return `${value.data?.cellId ?? ''}\n分组：${value.seriesName ?? ''}`
    }},
    xAxis: {type: 'value', name: `PC1 (${(100 * (props.projection.explained_variance_ratio[0] ?? 0)).toFixed(1)}%)`, nameLocation: 'middle', nameGap: 30, splitLine: {lineStyle: {color: '#e5e8e0'}}},
    yAxis: {type: 'value', name: `PC2 (${(100 * (props.projection.explained_variance_ratio[1] ?? 0)).toFixed(1)}%)`, nameLocation: 'middle', nameGap: 43, splitLine: {lineStyle: {color: '#e5e8e0'}}},
    series: groups.map(group => ({name: group, type: 'scatter', symbolSize: 6, itemStyle: {opacity: 0.65}, data: props.projection.points.filter(point => point.group === group).map(point => ({value: [point.x, point.y], cellId: point.cell_id}))})),
  }
}, [() => props.projection])
</script>
<template><div ref="el" class="pca-chart" role="img" :aria-label="`表达 PCA：展示 ${projection.plotted_cells} 个细胞`"></div></template>
<style scoped>.pca-chart{height:400px;width:100%}@media(max-width:600px){.pca-chart{height:320px}}</style>
