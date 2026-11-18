import { apiFetch } from './http'
import type { ResearchKind, ResearchSelection, ResearchResult, ResearchFinding } from '../types/research'
export const researchApi = {
  result: (kind: ResearchKind, id: string, signal?: AbortSignal) => apiFetch<ResearchResult>(`/research/results/${kind}/${encodeURIComponent(id)}`, {signal}),
  findings: (kind: ResearchKind, id: string, signal?: AbortSignal) => apiFetch<{items: ResearchFinding[]}>(`/research/findings`, {query:{record_kind:kind,record_id:id},signal}),
  save: (kind: ResearchKind, id: string, selection: ResearchSelection, note: string, signal?: AbortSignal) => apiFetch<ResearchFinding>('/research/findings', {method:'POST',body:{record_kind:kind,record_id:id,selection,note},signal}),
  export: (kind: ResearchKind, id: string, signal?: AbortSignal) => apiFetch<Record<string,unknown>>(`/research/results/${kind}/${encodeURIComponent(id)}/export`, {signal,timeoutMs:120000}),
}
