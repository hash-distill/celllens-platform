import { apiFetch, apiUrl } from './http'
import { useAuthStore } from '../stores/auth'
import type { DataCapabilities, DatasetMetadata, UserDataset, UserAnalysis, UserAnalysisRequest, UserAnalysisReport } from '../types/userData'

function headers() {return {'X-CSRF-Token': useAuthStore().user?.csrf_token ?? ''}}
export const userDataApi = {
  capabilities: () => apiFetch<DataCapabilities>('/data-capabilities'),
  datasets: (offset = 0) => apiFetch<{items: UserDataset[]; total: number}>('/datasets', {query: {offset, limit: 20}}),
  dataset: (id: string) => apiFetch<UserDataset>(`/datasets/${id}`),
  upload: (file: File, metadata: DatasetMetadata) => {
    const body = new FormData(); body.append('file', file); body.append('metadata', JSON.stringify(metadata))
    return apiFetch<UserDataset>('/datasets', {method: 'POST', body, headers: headers(), timeoutMs: 180000})
  },
  archive: (id: string) => apiFetch<UserDataset>(`/datasets/${id}/archive`, {method: 'POST', headers: headers()}),
  createAnalysis: (body: UserAnalysisRequest) => apiFetch<UserAnalysis>('/analyses', {method: 'POST', body, headers: headers()}),
  analyses: (offset = 0) => apiFetch<{items: UserAnalysis[]; total: number}>('/analyses', {query: {offset, limit: 20}}),
  analysis: (id: string) => apiFetch<UserAnalysis>(`/analyses/${id}`),
  report: (id: string) => apiFetch<UserAnalysisReport>(`/analyses/${id}/report`),
  sourceUrl: (id: string) => apiUrl(`/datasets/${id}/file`),
  artifactUrl: (id: string, filename: string) => apiUrl(`/analyses/${id}/files/${filename}`),
  createUser: (body: {username: string; password: string; role: 'user' | 'admin'}) => apiFetch('/auth/users', {method: 'POST', body, headers: headers()}),
}
