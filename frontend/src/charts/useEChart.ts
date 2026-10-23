import * as echarts from 'echarts/core'
import type { EChartsOption } from 'echarts'
import { BarChart, ScatterChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, TitleComponent, ToolboxComponent, DataZoomComponent, MarkLineComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, watch, type Ref, type WatchSource } from 'vue'
import { isDark } from '../stores/appearance'

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
    if (isDark.value) {
      const ink = '#e0e9e6', muted = '#a8bab6', border = '#39494b'
      // Adapt neutral labels and grid lines; preserve scientific source/delta colors.
      const neutral: Record<string, string> = {'#64748b': muted, '#172033': ink, '#111827': ink, '#334155': ink, '#475569': muted, '#eef2f7': border, '#e5e8e0': border, '#cbd5e1': border}
      function adapt(value: unknown) {
        if (!value || typeof value !== 'object') return
        for (const [key, item] of Object.entries(value)) {
          if (key === 'color' && typeof item === 'string' && neutral[item.toLowerCase()]) (value as Record<string,unknown>)[key] = neutral[item.toLowerCase()]
          else if (key !== 'data') adapt(item)
        }
      }
      adapt(option)
      option.textStyle = {...option.textStyle, color: ink}
      for (const axes of [option.xAxis, option.yAxis]) for (const axis of (Array.isArray(axes) ? axes : axes ? [axes] : [])) {
        axis.axisLabel = {...axis.axisLabel, color: muted}
        axis.nameTextStyle = {...axis.nameTextStyle, color: muted}
        axis.splitLine = {...axis.splitLine, lineStyle: {...axis.splitLine?.lineStyle, color: border}}
      }
      if (option.tooltip && !Array.isArray(option.tooltip)) option.tooltip = {...option.tooltip, backgroundColor: '#1d2b30', borderColor: border, textStyle: {color: ink}}
    }
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

  watch([...sources, isDark], render, { deep: true })

  onBeforeUnmount(() => {
    observer?.disconnect()
    chart?.dispose()
    chart = null
  })

  return { refresh: render, getChart: () => chart }
}
