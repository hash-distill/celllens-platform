import * as echarts from 'echarts/core'
import type { EChartsOption } from 'echarts'
import { BarChart, ScatterChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, TitleComponent, ToolboxComponent, DataZoomComponent, MarkLineComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, watch, type Ref, type WatchSource } from 'vue'

echarts.use([BarChart, ScatterChart, GridComponent, TooltipComponent, TitleComponent,
  ToolboxComponent, DataZoomComponent, MarkLineComponent, CanvasRenderer])

export const CHART_COLORS = {
  control: '#9AA5B1',
  predicted: '#79B7B2',
  observed: '#C7A45E',
  deltaDown: '#6BABA5',
  deltaUp: '#C47654',
} as const

const reducedMotion =
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * ECharts 容器组合式函数：只接收整理后的 option，
 * 负责初始化、响应尺寸、销毁与减少动画设置。
 */
export function useEChart(
  el: Ref<HTMLElement | null>,
  getOption: () => EChartsOption,
  sources: WatchSource<unknown>[],
): { refresh: () => void; getChart: () => echarts.ECharts | null } {
  let chart: echarts.ECharts | null = null
  let observer: ResizeObserver | null = null

  const render = () => {
    if (!el.value) return
    if (!chart) chart = echarts.init(el.value)
    const option = getOption()
    if (reducedMotion) option.animation = false
    chart.setOption(option, { notMerge: true })
  }

  onMounted(() => {
    render()
    if (el.value) {
      observer = new ResizeObserver(() => chart?.resize())
      observer.observe(el.value)
    }
  })

  watch(sources, render, { deep: true })

  onBeforeUnmount(() => {
    observer?.disconnect()
    chart?.dispose()
    chart = null
  })

  return { refresh: render, getChart: () => chart }
}
