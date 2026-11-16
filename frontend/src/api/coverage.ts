import { watch } from 'vue'
import { apiFetch } from './http'
import { accessSession } from '../stores/access'
import type { CoverageCatalogue } from '../types/coverage'
import { createCoverageCache } from '../utils/coverageCache'

export const coverageCatalog = createCoverageCache((source, signal) => apiFetch<CoverageCatalogue>('/coverage', {
  query: source.kind === 'run' ? { run_id: source.runId } : { cell_line: source.cellLine },
  signal, timeoutMs: 120000,
}))
// Never carry a private experiment's cached catalogue across access-session changes.
watch(accessSession, () => coverageCatalog.clear(), { flush: 'sync', deep: true })
