import { finiteValue } from './resultOverview'
import type { OverviewSource, OverviewTaskRow } from './resultOverview'

/** A common scale within each task, never a sum or ranking of unlike task scores. */
export function taskPair(row: OverviewTaskRow, source: OverviewSource) {
  const control = finiteValue(row.control)
  const target = finiteValue(source === 'run' ? row.predicted : row.observed)
  const delta = control === null || target === null ? null : target - control
  const minimum = Math.min(0, control ?? 0, target ?? 0)
  const maximum = Math.max(0, control ?? 0, target ?? 0)
  const span = maximum - minimum || 1
  return { ...row, control, target, delta,
    direction: delta === null ? 'missing' : delta > 0 ? 'up' : delta < 0 ? 'down' : 'same',
    controlPosition: control === null ? null : (control - minimum) / span,
    targetPosition: target === null ? null : (target - minimum) / span,
    zeroPosition: -minimum / span,
  }
}

export function scoreLabel(value: number | null, signed = false) {
  if (value === null || !Number.isFinite(value)) return '—'
  const text = value !== 0 && Math.abs(value) < .001 ? value.toExponential(2) : value.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
  return signed && value > 0 ? `+${text}` : text
}
