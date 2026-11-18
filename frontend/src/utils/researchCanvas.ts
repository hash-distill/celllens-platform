import type { OverviewTaskRow } from './resultOverview'

export type ProjectionSource = 'control' | 'observed' | 'predicted'
export interface ProjectionPoint { x: number; y: number; source: ProjectionSource; cell_id?: string; cell_index?: string | number }
export interface StructureTask extends OverviewTaskRow { rawCategory?: string | null }

/** The domain belongs to the saved projection, never to a visible subset. */
export function projectionBounds(points: Array<{ x: number; y: number }>) {
  const valid = points.filter(point => Number.isFinite(point.x) && Number.isFinite(point.y))
  function domain(axis: 'x' | 'y'): [number, number] {
    if (!valid.length) return [-1, 1]
    let low = Infinity, high = -Infinity
    for (const point of valid) { low = Math.min(low, point[axis]); high = Math.max(high, point[axis]) }
    const pad = (high - low || Math.max(Math.abs(low), 1)) * .08
    return [low - pad, high + pad]
  }
  return { x: domain('x'), y: domain('y') }
}

/** Only original, verified Task-Info System metadata may associate a structure. */
export function structureTasks(tasks: StructureTask[], structure: string | null): StructureTask[] {
  const system = structure === 'er' ? 'Processing in the ER' : structure === 'golgi' ? 'Processing in the Golgi' : null
  return system ? tasks.filter(task => task.rawCategory === system && [task.control, task.observed, task.predicted].some(value => typeof value === 'number' && Number.isFinite(value))) : []
}

export function escapeTooltip(value: unknown): string {
  return String(value ?? '未记录').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]!))
}
