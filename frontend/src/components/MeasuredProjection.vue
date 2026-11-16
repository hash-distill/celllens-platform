<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { EChartsOption } from 'echarts'
import * as echarts from 'echarts/core'
import { LegendComponent } from 'echarts/components'
import { CHART_COLORS, useEChart } from '../charts/useEChart'
import type { MeasuredProjection } from '../types/measured'
import type { ResearchSelection } from '../types/research'
import { escapeTooltip, projectionBounds } from '../utils/researchCanvas'
echarts.use([LegendComponent])
const props = defineProps<{ data: MeasuredProjection | null; embedding: 'pca' | 'umap'; analysisId: string }>()
const emit = defineEmits<{ selection: [value: ResearchSelection] }>()
const element = ref<HTMLElement | null>(null)
const group = ref<'all'|'control'|'observed'>('all')
const points = computed(() => (props.data?.points ?? []).filter(point => Number.isFinite(point.x) && Number.isFinite(point.y)))
const bounds = computed(() => projectionBounds(points.value))
const visible = computed(() => points.value.filter(point => group.value === 'all' || point.source === group.value))
watch(() => props.analysisId, () => { group.value = 'all' })
watch([group, () => props.embedding], () => emit('selection', { layer: 'expression', projection_id: props.embedding, group_id: group.value === 'all' ? undefined : group.value }), { immediate: true })
function option(): EChartsOption {
  return {
    animation: false,
    legend: { top: 0, left: 0, selectedMode: false, data: ['实测对照', '扰动实测'], textStyle: { color: '#475569' } },
    grid: { top: 45, left: 65, right: 25, bottom: 65 },
    tooltip: { trigger: 'item', confine: true, formatter: (params: unknown) => { const p = params as { seriesName: string; data: { point: NonNullable<MeasuredProjection['points']>[number] } }, point=p.data.point; return `${escapeTooltip(p.seriesName)}<br/>cell_id: ${escapeTooltip(point.cell_id)}<br/>source: ${escapeTooltip(point.source)}<br/>x: ${point.x.toFixed(3)}<br/>y: ${point.y.toFixed(3)}` } },
    toolbox: { feature: { saveAsImage: { title: '下载 PNG', name: `${props.analysisId}_${props.embedding}`, pixelRatio: 2 }, restore: { title: '重置缩放' } } },
    xAxis: { type: 'value', name: props.embedding === 'pca' ? 'PC 1' : 'UMAP 1', nameLocation: 'middle', nameGap: 30, min: bounds.value.x[0], max: bounds.value.x[1], axisLabel: { formatter: (value: number) => Number(value.toPrecision(3)).toLocaleString('zh-CN') }, splitLine: { lineStyle: { color: '#eef2f7' } } },
    yAxis: { type: 'value', name: props.embedding === 'pca' ? 'PC 2' : 'UMAP 2', min: bounds.value.y[0], max: bounds.value.y[1], axisLabel: { formatter: (value: number) => Number(value.toPrecision(3)).toLocaleString('zh-CN') }, splitLine: { lineStyle: { color: '#eef2f7' } } },
    dataZoom: [{ type: 'inside', xAxisIndex: 0, filterMode: 'none', zoomOnMouseWheel: 'ctrl', moveOnMouseWheel: false }, { type: 'inside', yAxisIndex: 0, filterMode: 'none', zoomOnMouseWheel: 'ctrl', moveOnMouseWheel: false }, { type: 'slider', xAxisIndex: 0, filterMode: 'none', bottom: 0 }],
    series: (['control', 'observed'] as const).filter(source => group.value === 'all' || group.value === source).map(source => ({ name: source === 'control' ? '实测对照' : '扰动实测', type: 'scatter', symbolSize: 5, itemStyle: { color: CHART_COLORS[source], opacity: .7 }, data: points.value.filter(p => p.source === source).map(point => ({value:[point.x, point.y],point})) })),
  }
}
const { getChart } = useEChart(element, option, [() => props.data, () => props.embedding, group])
function resetZoom() { getChart()?.dispatchAction({type:'dataZoom',batch:[0,1,2].map(dataZoomIndex=>({dataZoomIndex,start:0,end:100}))}) }
</script>
<template><div class="measured-plot"><div class="btn-row projection-toolbar"><button v-for="source in (['all','control','observed'] as const)" :key="source" class="btn btn-sm" :aria-pressed="group===source" @click="group=source">{{{all:'全部群体',control:'实测对照',observed:'扰动实测'}[source]}}</button><button class="btn btn-sm" @click="resetZoom">恢复完整范围</button></div><div ref="element" class="plot-canvas" role="img" :aria-label="`${embedding.toUpperCase()} 实测对照与扰动细胞分布`"/><p>所选群体 {{visible.length}} / 已保存 {{points.length}} 条坐标；全部群体共用固定轴域。Ctrl + 滚轮缩放，拖动平移。坐标表示表达空间位置，不代表细胞运动。</p></div></template>
<style scoped>.plot-canvas{height:360px;width:100%}p{font-size:12px;line-height:1.8;color:var(--muted);margin:12px 0 0}.projection-toolbar{margin-bottom:14px}.projection-toolbar [aria-pressed=true]{background:var(--primary-weak);border-color:var(--primary);color:var(--primary-strong)}</style>
