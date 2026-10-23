import type { ExperimentRecord } from '../types/experiment'
import type { MeasuredAnalysis } from '../types/measured'

export type RecordCategory = 'all' | 'measured' | 'predicted'
export type RecordStatusFilter = 'all' | 'active' | 'completed' | 'failed' | 'cancelled' | 'interrupted'
export interface ResearchRecord {
  key: string
  id: string
  category: Exclude<RecordCategory, 'all'>
  title: string
  subtitle: string
  sourceLabel: string
  status: string
  progress: number
  createdAt: string
  target: string
}
export interface RecordFilters {
  category: RecordCategory
  status: RecordStatusFilter
  query: string
  resultsOnly: boolean
}

export function measuredRecord(record: MeasuredAnalysis): ResearchRecord {
  return {
    key: `measured:${record.id}`, id: record.id, category: 'measured',
    title: `${record.cell_line} / ${record.perturbation}`,
    subtitle: `请求上限 ${record.max_cells} 个实测细胞`, sourceLabel: '公开实测',
    status: record.status, progress: record.progress, createdAt: record.created_at,
    target: `/measured/${encodeURIComponent(record.id)}`,
  }
}

export function predictedRecord(record: ExperimentRecord, mock = false): ResearchRecord {
  return {
    key: `predicted:${record.id}`, id: record.id, category: 'predicted',
    title: record.title, subtitle: record.subtitle,
    sourceLabel: mock || record.run.result_kind === 'synthetic_demo' ? '合成示例' : '模型预测',
    status: record.status, progress: record.run.stage_progress, createdAt: record.created_at,
    target: `/runs/${encodeURIComponent(record.id)}`,
  }
}

function databaseUtcTime(raw: string): number {
  const timestamp = Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw) ? raw : `${raw}Z`)
  return Number.isFinite(timestamp) ? timestamp : 0
}

export function selectRecords(records: ResearchRecord[], filters: RecordFilters): ResearchRecord[] {
  const query = filters.query.trim().toLocaleLowerCase()
  return records.filter(record => {
    if (filters.category !== 'all' && record.category !== filters.category) return false
    if (filters.resultsOnly && record.status !== 'completed') return false
    if (filters.status === 'active' && ['completed', 'failed', 'cancelled', 'interrupted'].includes(record.status)) return false
    if (!['all', 'active'].includes(filters.status) && record.status !== filters.status) return false
    return !query || `${record.id} ${record.title} ${record.subtitle}`.toLocaleLowerCase().includes(query)
  }).sort((left, right) => databaseUtcTime(right.createdAt) - databaseUtcTime(left.createdAt) || left.key.localeCompare(right.key))
}

export async function collectRecordPages<RecordItem extends { id: string }>(
  fetchPage: (limit: number, offset: number) => Promise<{ items: RecordItem[]; total: number }>,
  signal?: AbortSignal,
): Promise<RecordItem[]> {
  const records: RecordItem[] = []
  const identifiers = new Set<string>()
  let total: number | undefined
  do {
    signal?.throwIfAborted()
    const page = await fetchPage(100, records.length)
    signal?.throwIfAborted()
    if ((total !== undefined && page.total !== total) || (!page.items.length && records.length < page.total)) {
      throw new Error('记录列表已变化或未完整返回，请刷新重试。')
    }
    total = page.total
    for (const record of page.items) {
      if (identifiers.has(record.id)) throw new Error('记录列表已变化，请刷新重试。')
      identifiers.add(record.id)
      records.push(record)
    }
    if (records.length > total) throw new Error('记录列表未完整返回，请刷新重试。')
  } while (records.length < total)
  return records
}
