import { isMockEnabled } from '../api/mockFlag'

/** Separate demo history from API history. Migrate legacy real records only. */
export function historyKey(base: string): string {
  return `${base}.${isMockEnabled() ? 'mock' : 'api'}.records-v2`
}

export function readHistory<T extends { run_id: string }>(base: string): T[] {
  try {
    const key = historyKey(base)
    const raw = localStorage.getItem(key)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is T =>
      item && typeof item.run_id === 'string' &&
      item.run_id.startsWith('mock_run_') === isMockEnabled(),
    )
  } catch {
    return []
  }
}
