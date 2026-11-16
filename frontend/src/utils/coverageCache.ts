import type { CoverageCatalogue } from '../types/coverage'

export type CoverageSource = { kind: 'model'; cellLine?: string } | { kind: 'run'; runId: string }
export interface CoverageSnapshot { data: CoverageCatalogue; fetchedAt: number }
export const COVERAGE_CACHE_TTL_MS = 5 * 60 * 1000
export function coverageSourceKey(source: CoverageSource): string {
  return JSON.stringify(source.kind === 'run' ? ['run', source.runId] : ['model', source.cellLine || ''])
}
const cancelled = () => new DOMException('请求已取消', 'AbortError')

/** Memory-only LRU. Consumers cancel independently; the final consumer aborts the transport. */
export function createCoverageCache(
  fetcher: (source: CoverageSource, signal: AbortSignal) => Promise<CoverageCatalogue>,
  options: { ttlMs?: number; maxEntries?: number; now?: () => number } = {},
) {
  const now = options.now ?? Date.now, ttl = options.ttlMs ?? COVERAGE_CACHE_TTL_MS
  const capacity = Math.max(1, options.maxEntries ?? 4)
  const entries = new Map<string, CoverageSnapshot>()
  type Pending = { controller: AbortController; promise: Promise<CoverageSnapshot>; consumers: number }
  const pending = new Map<string, Pending>()
  function peek(source: CoverageSource): CoverageSnapshot | null {
    const key = coverageSourceKey(source), entry = entries.get(key)
    if (!entry) return null
    if (now() - entry.fetchedAt >= ttl) { entries.delete(key); return null }
    entries.delete(key); entries.set(key, entry)
    return entry
  }
  function load(source: CoverageSource, signal: AbortSignal, force = false): Promise<CoverageSnapshot> {
    if (signal.aborted) return Promise.reject(cancelled())
    const cached = force ? null : peek(source)
    if (cached) return Promise.resolve(cached)
    const key = coverageSourceKey(source)
    let request = pending.get(key)
    if (!request) {
      const controller = new AbortController()
      // Start in a microtask so all same-tick callers can subscribe before completion.
      const promise = Promise.resolve().then(() => fetcher(source, controller.signal)).then(data => {
        if (controller.signal.aborted) throw cancelled()
        const snapshot = { data, fetchedAt: now() }
        entries.delete(key); entries.set(key, snapshot)
        while (entries.size > capacity) entries.delete(entries.keys().next().value!)
        return snapshot
      }).finally(() => { if (pending.get(key)?.controller === controller) pending.delete(key) })
      request = { controller, promise, consumers: 0 }
      pending.set(key, request)
    }
    const current = request
    current.consumers++
    return new Promise((resolve, reject) => {
      let settled = false
      const finish = (callback: () => void) => {
        if (settled) return
        settled = true; signal.removeEventListener('abort', abort); current.controller.signal.removeEventListener('abort', abort); current.consumers--
        if (current.consumers === 0 && pending.get(key) === current) {
          pending.delete(key); current.controller.abort()
        }
        callback()
      }
      const abort = () => finish(() => reject(cancelled()))
      signal.addEventListener('abort', abort, { once: true })
      current.controller.signal.addEventListener('abort', abort, { once: true })
      current.promise.then(value => finish(() => resolve(value)), error => finish(() => reject(error)))
    })
  }
  function clear() {
    entries.clear()
    for (const request of pending.values()) request.controller.abort()
    pending.clear()
  }
  return { peek, load, clear }
}
