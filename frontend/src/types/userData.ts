export interface ResearchUser { id: string; username: string; role: 'admin' | 'user'; csrf_token: string }
export interface DataCapabilities {
  worker_enabled: boolean; expression_ready: boolean; metabolism_ready: boolean
  max_upload_bytes: number; max_user_storage_bytes: number; max_cells: number; max_genes: number
  max_matrix_values: number; state_user_prediction_enabled: boolean
}
export interface DatasetMetadata {
  name: string; expression_scale: 'raw_counts' | 'cp10k' | 'log1p_cp10k'; input_layer: string
  matrix_scope: 'full_library' | 'selected_panel'; total_counts_key: string | null
  organism: 'human'; cell_context: string; description: string
}
export interface UserDataset {
  id: string; name: string; filename: string; sha256: string; size_bytes: number
  metadata: DatasetMetadata; archived: boolean; created_at: string
  summary: { n_cells: number; n_genes: number; group_columns: Record<string, string[]>; warnings: string[]
    state_compatibility: {message: string; registered_background: boolean; required_genes?: number
      matched_genes?: number; missing_genes: string[]; missing_columns: string[]} }
}
export interface UserAnalysisRequest {
  dataset_id: string; kind: 'explore' | 'metabolism'; group_key: string | null
  reference_group: string | null; seed: number
}
export interface UserAnalysis {
  id: string; dataset_id: string; kind: 'explore' | 'metabolism'
  status: 'queued' | 'running' | 'completed' | 'failed'; request: UserAnalysisRequest
  error_message: string | null; artifacts: Record<string, {sha256: string; size_bytes: number}>
  created_at: string; updated_at: string
}
export interface ExpressionGene {
  gene: string; group: string; n_cells: number; mean_log1p_cp10k: number
  detection_fraction: number; reference_mean_log1p_cp10k?: number; delta_log1p_cp10k?: number
}
export interface UserAnalysisReport {
  analysis_id: string; dataset_id: string; kind: 'explore' | 'metabolism'; warnings: string[]
  qc: {n_cells: number; n_genes: number; zero_expression_cells: number; median_detected_genes: number; groups: Record<string, number>}
  comparison: {method: string; group_key: string | null; reference_group: string | null; interpretation: string}
  provenance: {source_sha256: string; analysis_version: string; metadata: DatasetMetadata}
  projection: {method: 'PCA'; total_cells: number; plotted_cells: number; seed: number
    explained_variance_ratio: number[]; selected_genes: string[]
    points: {cell_id: string; group: string; x: number; y: number}[]}
  genes: ExpressionGene[]
  metabolism?: {database_version: string; n_tasks: number; n_reactions: number
    n_tasks_database: number; n_reactions_database: number; unscored_tasks: string[]; score_scope: string
    official_summary: Record<string, number>; interpretation: string
    tasks: {id: string; group: string; mean_score: number; reference_mean?: number; delta?: number}[]}
}
