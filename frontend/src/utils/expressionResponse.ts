import { finiteValue } from './resultOverview'
import type { OverviewRow, OverviewSource } from './resultOverview'
export function expressionPairs(rows: OverviewRow[], kind: OverviewSource) {
  return rows.map(row => {
    const control = finiteValue(row.control), target = finiteValue(kind === 'run' ? row.predicted : row.observed)
    return { id: row.id, control, target, delta: control === null || target === null ? null : target - control }
  })
}
export type ExpressionPair = ReturnType<typeof expressionPairs>[number]
export function strongestGenes(rows: ExpressionPair[], limit = 12) {
  return rows.filter(row => row.delta !== null).slice().sort((a, b) => Math.abs(b.delta!) - Math.abs(a.delta!) || a.id.localeCompare(b.id)).slice(0, limit)
}
/** Deterministic display sample; all source rows remain available for ranking and CSV. */
export function scatterSample(rows: ExpressionPair[], limit = 2000) {
  const paired = rows.filter(row => row.control !== null && row.target !== null)
  if (paired.length <= limit) return paired
  return Array.from({length: limit}, (_, index) => paired[Math.floor(index * paired.length / limit)]!)
}
