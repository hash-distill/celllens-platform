import { apiFetch, apiUrl } from './http'
import type { DataCapabilities, DatasetMetadata, UserDataset, UserAnalysis, UserAnalysisRequest, UserAnalysisReport } from '../types/userData'

export const userDataApi = {
  capabilities: () => apiFetch<DataCapabilities>('/data-capabilities'),
  datasets: (offset = 0, q = '') => apiFetch<{items: UserDataset[]; total: number}>('/datasets', {query: {offset, limit: 20, q}}),
  dataset: (id: string) => apiFetch<UserDataset>(`/datasets/${id}`),
  upload: (file: File, metadata: DatasetMetadata) => {
    const body = new FormData(); body.append('file', file); body.append('metadata', JSON.stringify(metadata))
    return apiFetch<UserDataset>('/datasets', {method: 'POST', body})
  },
  archive: (id: string) => apiFetch<UserDataset>(`/datasets/${id}/archive`, {method: 'POST'}),
  analyses: (offset = 0, datasetId = '', status = '') => apiFetch<{items: UserAnalysis[]; total: number}>('/analyses', {query: {offset, limit: 20, dataset_id: datasetId || undefined, status: status || undefined}}),
  createAnalysis: (body: UserAnalysisRequest) => apiFetch<UserAnalysis>('/analyses', {method: 'POST', body}),
  analysis: (id: string) => apiFetch<UserAnalysis>(`/analyses/${id}`),
  report: (id: string) => apiFetch<UserAnalysisReport>(`/analyses/${id}/report`),
  sourceUrl: (id: string) => apiUrl(`/datasets/${id}/file`),
  artifactUrl: (id: string, file: string) => apiUrl(`/analyses/${id}/files/${encodeURIComponent(file)}`),
}
