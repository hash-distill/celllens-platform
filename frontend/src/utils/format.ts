import type { EvidenceLevel, RunMode, RunStatus } from '../types/run'

/** 显示数值；null 显示「未提供」，绝不回退为 0 */
export function fmtNumber(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '未提供'
  if (value === 0) return '0'
  const abs = Math.abs(value)
  if (abs >= 10000 || abs < 0.0001) return value.toExponential(2)
  return String(Number(value.toFixed(digits)))
}

/** 带正负号的变化量 */
export function fmtDelta(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '未提供'
  const body = fmtNumber(Math.abs(value), digits)
  if (value > 0) return `+${body}`
  if (value < 0) return `-${body}`
  return '0'
}

/** 0-1 比例转百分比 */
export function fmtPercent(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '未提供'
  return `${(value * 100).toFixed(digits)}%`
}

/**
 * 服务端时间显示。
 * 后端时间字符串可能没有时区信息：此时标注「服务端记录时间」，
 * 不擅自追加 UTC，也不做未知时区换算。
 */
export function hasTimezone(raw: string): boolean {
  return /([zZ]|[+-]\d{2}:?\d{2})\s*$/.test(raw.trim())
}

export function fmtServerTime(raw: string | null | undefined): string {
  if (!raw) return '未提供'
  const body = raw.replace('T', ' ').replace(/\.\d+/, '').trim()
  return hasTimezone(raw) ? body : `${body}（服务端记录时间）`
}

export const MODE_LABEL: Record<RunMode, string> = {
  online: '在线推演',
  precomputed: '结果回放',
  validation: '实测对照',
}

export const STATUS_LABEL: Record<RunStatus, string> = {
  queued: '等待执行',
  state_running: '正在生成扰动预测',
  adapting: '正在对齐表达数据',
  metabolic_running: '正在分析基因与代谢结果',
  validating: '正在校验并整理结果',
  completed: '分析完成',
  failed: '分析失败',
}

export const EVIDENCE_LABEL: Record<EvidenceLevel, string> = {
  supported: '覆盖支持',
  exploratory: '探索性',
  insufficient: '证据不足',
}

export const SOURCE_LABEL = {
  control: '对照',
  predicted: '预测',
  observed: '观测',
} as const

/** 短运行编号（界面紧凑处展示） */
export function shortRunId(runId: string): string {
  return runId.length > 18 ? `${runId.slice(0, 14)}…` : runId
}
