export type MeasuredCellLine = 'K562' | 'RPE1' | 'Jurkat' | 'HepG2'
export type MeasuredStatus = 'queued' | 'preparing' | 'analysing' | 'completed' | 'failed' | 'cancelled' | 'interrupted'
export type MeasuredTableKind = 'genes' | 'tasks' | 'reactions'
export type MeasuredDownloadKind = 'bundle' | MeasuredTableKind | 'projection' | 'report'
export interface MeasuredRequest { cell_line: MeasuredCellLine; perturbation: string; max_cells: number; seed: number }
export interface MeasuredRow {
  gene?: string; task?: string; reaction?: string; label?: string; category?: string | null; subcategory?: string | null
  control: number | null; observed: number | null; observed_delta: number | null; gene_fraction?: number | null
}
export interface MeasuredCounts { control: number; observed: number }
export interface MeasuredSummary {
  analysis_id: string; source_kind: 'measured'; cell_line: string; perturbation: string
  input_counts: MeasuredCounts; counts: MeasuredCounts; source_cell_count: number; gene_count: number
  expression_units: string; top_genes: MeasuredRow[]
  metabolism: { available: boolean; database_version?: string; task_count?: number; reaction_count?: number; top_tasks?: MeasuredRow[]; reason?: string }
  projections: { pca: { available: boolean; method?: string; reason?: string }; umap: { available: boolean; method?: string; reason?: string } }
  batch_matching: Record<string, unknown>; warnings: string[]; provenance: Record<string, unknown>; limitations?: string[]
}
export interface MeasuredAnalysis extends Omit<MeasuredRequest, 'cell_line'> {
  dataset_id?: string | null; condition_id?: string | null
  cell_line: string; import_id?: string | null; source?: { kind?: string; import_id?: string; [key: string]: unknown }
  id: string; status: MeasuredStatus; progress: number; message: string | null
  created_at: string; updated_at: string; source_kind: 'measured'; summary: MeasuredSummary | null; error_message: string | null
}
export interface MeasuredPage<T> { items: T[]; total: number; limit: number; offset: number }
export interface MeasuredTable extends MeasuredPage<MeasuredRow> { units: string | Record<string, unknown> }
export interface MeasuredProjection {
  method: string; points: Array<{ x: number; y: number; source: 'control' | 'observed'; cell_id: string }>
  counts: MeasuredCounts; gene_count: number
}
export interface MeasuredCoverage {
  source_status: 'measured' | 'not_in_source' | 'unknown'; source_cell_count: number | null
  local_verified: boolean; local_measured_cells: number; model_supported: boolean
}
