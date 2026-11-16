export type ResearchKind = 'measured' | 'prediction'
export interface ResearchSelection { gene_id?: string; task_id?: string; group_id?: 'control'|'observed'|'predicted'; layer?: 'expression'|'function'|'coverage'|'structure'; projection_id?: 'pca'|'umap' }
export interface ResearchPopulation {
  availability: { available: boolean; reason?: string | null }
  groups?: Array<{ id: string; source_kind: string; count: number | null }>
  provenance?: { comparison_sha256?: string; manifest_sha256?: string; [key: string]: unknown }
  batch_sensitivity?: { status: string; reason?: string; baseline_conclusion_consistent?: boolean }
  warnings?: string[]
}
export interface ResearchResult {
  schema_version: string; result_id: string; record_kind: ResearchKind; record_id: string; state: string; source_kind: string
  background: { cell_line: string }; target: { perturbation: string }
  groups: Array<{ id: string; source_kind: string; count: number | null }>
  units: Record<string, string | null>; coverage: Record<string, unknown>
  availability: Record<string, { available: boolean; reason?: string | null }>
  provenance: { manifest_sha256?: string | null; fingerprint_basis?: string; [key: string]: unknown }
  references: Record<string, unknown>; limitations: string[]; warnings: string[]
  populations?: { original: ResearchPopulation; matched_comparison: ResearchPopulation }
}
export interface ResearchFinding { id: string; record_kind: ResearchKind; record_id: string; selection: ResearchSelection; note: string; manifest_sha256?: string | null; created_at: string }
