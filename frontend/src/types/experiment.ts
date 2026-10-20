import type { RunRecord, RunStatus } from './run'

export interface ExperimentRecord {
  id: string; source: 'online'; status: RunStatus
  title: string; subtitle: string
  created_at: string; run: RunRecord
}
export interface ExperimentQuery {
  limit: number; offset: number; q: string
  status: 'all' | 'active' | 'completed' | 'failed'; source?: 'online'
}
export interface ExperimentList {
  items: ExperimentRecord[]; total: number; limit: number; offset: number
}
