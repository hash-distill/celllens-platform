import { apiFetch } from './http'
import { fetchDownload } from '../utils/download'

export type Availability = 'all' | 'measured' | 'missing' | 'unknown'
export interface CatalogPair {
  cell_line: string
  perturbation: string
  source_cell_count: number | null
  source_status: 'measured' | 'not_in_source' | 'unknown'
  local_verified: boolean
  local_measured_cells: number
  model_supported: boolean
  official_split: 'test' | 'val' | 'not_declared_held_out' | 'unknown'
  training_exclusion_verified: false
  generalization_verified: false
  recommended_action: 'measured' | 'predict_exploratory' | 'unsupported' | 'check_source'
}
export interface CatalogQuery {
  cell_line?: string
  query?: string
  availability?: Availability
  model_supported?: boolean
  limit?: number
  offset?: number
}
export interface CatalogResponse {
  items: CatalogPair[]
  total: number
  source_verified: boolean
  source: { repo: string; revision: string; url: string; scope: string }
  summary: {
    pairs: number
    measured_pairs: number
    model_supported_pairs: number
    model_supported_unmeasured_pairs: number | null
    unknown_pairs: number
    local_verified_pairs: number
    contexts: { cell_line: string; source_total_cells: number | null; measured_pairs: number;
      model_supported_pairs: number; model_supported_unmeasured_pairs: number | null }[]
  }
}
export const dataCatalogApi = {
  query: (query: CatalogQuery, signal?: AbortSignal) =>
    apiFetch<CatalogResponse>('/data-catalog', { query: { ...query }, signal }),
  pair: (cell_line: string, perturbation: string, signal?: AbortSignal) =>
    apiFetch<CatalogPair>('/data-catalog/pair', { query: { cell_line, perturbation }, signal }),
  download: (query: CatalogQuery, signal?: AbortSignal) =>
    fetchDownload('/data-catalog/download.csv', { format: 'csv', filename: 'celllens-data-catalog.csv',
      query: { cell_line: query.cell_line, query: query.query, availability: query.availability,
        model_supported: query.model_supported }, signal }),
}
