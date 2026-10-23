export type OverviewSource = 'run' | 'measured'
export interface OverviewRow {
  id: string
  label?: string
  control: number | null
  predicted?: number | null
  observed?: number | null
  delta: number | null
}
export interface OverviewTaskRow extends OverviewRow {
  coverage?: number | null
  category?: string
}
export interface OverviewCounts {
  control?: number | null
  predicted?: number | null
  observed?: number | null
}

export function finiteValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function coverageState(value: unknown): 'full' | 'partial' | 'unknown' {
  const coverage = finiteValue(value)
  if (coverage === null || coverage < 0 || coverage > 1) return 'unknown'
  return coverage === 1 ? 'full' : 'partial'
}

function compareChange(first: OverviewRow, second: OverviewRow): number {
  const firstDelta = finiteValue(first.delta)
  const secondDelta = finiteValue(second.delta)
  if (firstDelta === null && secondDelta !== null) return 1
  if (firstDelta !== null && secondDelta === null) return -1
  return Math.abs(secondDelta ?? 0) - Math.abs(firstDelta ?? 0) || first.id.localeCompare(second.id)
}

export function rankGenes(rows: OverviewRow[]): OverviewRow[] {
  return [...rows].sort(compareChange)
}

export function rankTasks(rows: OverviewTaskRow[]): OverviewTaskRow[] {
  return [...rows].sort((first, second) => {
    const firstCoverage = coverageState(first.coverage) === 'unknown' ? -1 : first.coverage!
    const secondCoverage = coverageState(second.coverage) === 'unknown' ? -1 : second.coverage!
    return secondCoverage - firstCoverage || compareChange(first, second)
  })
}

export function comparisonBars(row: OverviewRow, sourceKind: OverviewSource) {
  const sources = sourceKind === 'run' ? ['control', 'predicted', 'observed'] as const : ['control', 'observed'] as const
  const values = sources.map(source => finiteValue(row[source]))
  const present = values.filter((value): value is number => value !== null)
  const minimum = Math.min(0, ...present)
  const maximum = Math.max(0, ...present)
  const span = maximum - minimum || 1
  const zero = -minimum / span * 100
  return {
    domain: [minimum, maximum],
    zero,
    hasValues: present.length > 0,
    bars: sources.map((source, index) => {
      const value = values[index]!
      return {
        source,
        value,
        start: value === null ? null : (Math.min(0, value) - minimum) / span * 100,
        width: value === null ? null : Math.abs(value) / span * 100,
      }
    }),
  }
}
