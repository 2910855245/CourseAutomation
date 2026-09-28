/**
 * ECharts 按需注册 + 图表配色。
 *
 * 只注册实际用到的图表/组件（而不是 `import * as echarts`），
 * 避免整包进入 vendor-echarts。新增图表类型时在这里补注册。
 */
import { use } from 'echarts/core'
import { BarChart, LineChart, GaugeChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([BarChart, LineChart, GaugeChart, GridComponent, TooltipComponent, CanvasRenderer])

export interface ChartPalette {
  /** 轴线 / 刻度文字 */
  axis: string
  /** 分隔线 */
  split: string
  /** 正文（tooltip 文字） */
  text: string
  tooltipBg: string
  tooltipBorder: string
  primary: string
  info: string
  success: string
  warning: string
  danger: string
}

/** 与 main.css 的变量族保持一致（改色时两处一起改） */
export function chartPalette(isDark: boolean): ChartPalette {
  return isDark
    ? {
        axis: '#74757f',
        split: 'rgba(255, 255, 255, .08)',
        text: '#f2f2f5',
        tooltipBg: '#1a1a1f',
        tooltipBorder: '#31313a',
        primary: '#3d94ea',
        info: '#60a5fa',
        success: '#4ade80',
        warning: '#fbbf24',
        danger: '#f87171',
      }
    : {
        axis: '#90919a',
        split: 'rgba(20, 20, 23, .08)',
        text: '#141417',
        tooltipBg: '#ffffff',
        tooltipBorder: '#e0e0e4',
        primary: '#0071e3',
        info: '#0b6bcb',
        success: '#15803d',
        warning: '#b45309',
        danger: '#dc2626',
      }
}
