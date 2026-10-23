<script setup lang="ts">
import { ref } from 'vue'
import type { EChartsOption } from 'echarts'
import * as echarts from 'echarts/core'
import { LegendComponent } from 'echarts/components'
import { CHART_COLORS, useEChart } from '../charts/useEChart'
import type { MeasuredProjection } from '../types/measured'
echarts.use([LegendComponent])
const props = defineProps<{ data: MeasuredProjection | null; embedding: 'pca' | 'umap'; analysisId: string }>()
const element = ref<HTMLElement | null>(null)
function option(): EChartsOption {
  return {
    animation: false,
    legend: { top: 0, left: 0, data: ['实测对照', '实测扰动'], textStyle: { color: '#475569' } },
    grid: { top: 45, left: 65, right: 25, bottom: 65 },
    tooltip: { trigger: 'item', formatter: (params: unknown) => { const p = params as { seriesName?: string; data?: number[] }; return `${p.seriesName ?? ''}<br/>x: ${Number(p.data?.[0]).toFixed(3)}<br/>y: ${Number(p.data?.[1]).toFixed(3)}` } },
    toolbox: { feature: { saveAsImage: { title: '下载 PNG', name: `${props.analysisId}_${props.embedding}`, pixelRatio: 2 }, restore: { title: '重置缩放' } } },
    xAxis: { type: 'value', name: props.embedding === 'pca' ? 'PC 1' : 'UMAP 1', nameLocation: 'middle', nameGap: 30, scale: true, splitLine: { lineStyle: { color: '#eef2f7' } } },
    yAxis: { type: 'value', name: props.embedding === 'pca' ? 'PC 2' : 'UMAP 2', scale: true, splitLine: { lineStyle: { color: '#eef2f7' } } },
    dataZoom: [{ type: 'inside', xAxisIndex: 0 }, { type: 'inside', yAxisIndex: 0 }, { type: 'slider', xAxisIndex: 0, bottom: 0 }],
    series: (['control', 'observed'] as const).map(source => ({ name: source === 'control' ? '实测对照' : '实测扰动', type: 'scatter', symbolSize: 5, itemStyle: { color: CHART_COLORS[source], opacity: .6 }, data: (props.data?.points ?? []).filter(p => p.source === source && Number.isFinite(p.x) && Number.isFinite(p.y)).map(p => [p.x, p.y]) })),
  }
}
useEChart(element, option, [() => props.data, () => props.embedding])
</script>
<template><div class="measured-plot"><div ref="element" class="plot-canvas" role="img" :aria-label="`${embedding.toUpperCase()} 实测对照与扰动细胞分布`"/><p>滚轮缩放，拖动查看；点击图例可切换群体显示。坐标表示表达空间位置，不代表细胞运动。</p></div></template>
<style scoped>.plot-canvas{height:400px;width:100%}p{font-size:11px;color:var(--muted);margin:12px 0 0}</style>
