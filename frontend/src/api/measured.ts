import { apiFetch, apiFetchRaw, parseDetail } from './http'
import { fetchDownload, type DownloadFile } from '../utils/download'
import { toFiniteNumber } from '../utils/number'
import type { MeasuredAnalysis, MeasuredRequest, MeasuredPage, MeasuredTable, MeasuredTableKind, MeasuredProjection, MeasuredDownloadKind, MeasuredCoverage } from '../types/measured'
import type { PerturbationList } from '../types/run'

const root = '/measured/analyses'
const itemPath = (id: string) => `${root}/${encodeURIComponent(id)}`
export const measuredApi = {
  expressionSummary: (id: string, signal?: AbortSignal) => apiFetch<MeasuredTable & {record_id:string}>(`/figures/measured/${encodeURIComponent(id)}/expression-summary`, {signal}),
  list: (limit = 20, offset = 0, signal?: AbortSignal) => apiFetch<MeasuredPage<MeasuredAnalysis>>(root, { query: { limit, offset }, signal }),
  create: (body: MeasuredRequest, signal?: AbortSignal) => apiFetch<MeasuredAnalysis>(root, { method: 'POST', body, signal }),
  get: (id: string, signal?: AbortSignal) => apiFetch<MeasuredAnalysis>(itemPath(id), { signal }),
  cancel: (id: string, signal?: AbortSignal) => apiFetch<MeasuredAnalysis>(`${itemPath(id)}/cancel`, { method: 'POST', signal }),
  async table(id: string, kind: MeasuredTableKind, query: string, limit: number, offset: number, signal?: AbortSignal): Promise<MeasuredTable> {
    const data = await apiFetch<MeasuredTable>(`${itemPath(id)}/table`, { query: { kind, query, limit, offset }, signal })
    return { ...data, items: data.items.map(row => ({ ...row, control: toFiniteNumber(row.control), observed: toFiniteNumber(row.observed), observed_delta: toFiniteNumber(row.observed_delta), gene_fraction: toFiniteNumber(row.gene_fraction) })) }
  },
  projection: (id: string, embedding: 'pca' | 'umap', signal?: AbortSignal) => apiFetch<MeasuredProjection>(`${itemPath(id)}/projection`, { query: { embedding }, signal }),
  coverage: (cell_line: string, perturbation: string, signal?: AbortSignal) => apiFetch<MeasuredCoverage>('/data-catalog/pair', { query: { cell_line, perturbation }, signal }),
  choices: (cell_line: string, signal?: AbortSignal) => apiFetch<PerturbationList>('/catalog/perturbations', { query: { cell_line, mode: 'measured' }, signal }),
  async download(id: string, kind: MeasuredDownloadKind, signal?: AbortSignal): Promise<DownloadFile> {
    const path = `${itemPath(id)}/download`
    if (kind !== 'report') {
      const format = kind === 'bundle' ? 'zip' : kind === 'projection' ? 'json' : 'csv'
      return fetchDownload(path, { query: { kind }, format, filename: `${id}_${kind}.${format}`, signal })
    }
    // The shared download validator intentionally excludes HTML. Validate this report explicitly.
    const raw = await apiFetchRaw(path, { query: { kind }, responseType: 'blob', signal, timeoutMs: 120000 })
    if (!raw.ok) throw new Error(parseDetail((raw.data as { detail?: unknown } | null)?.detail, `报告下载失败：HTTP ${raw.status}`).message)
    if (!(raw.data instanceof Blob) || !/^text\/html(?:;|$)/i.test(raw.data.type) || !/<(?:!doctype html|html)[\s>]/i.test(await raw.data.slice(0, 1024).text())) throw new Error('报告未返回有效 HTML 文件')
    if (signal?.aborted) throw new Error('下载已取消')
    return { blob: raw.data, filename: `${id}_report.html` }
  },
}
