export interface ComparisonRow {
  id: string
  control: number
  predicted: number
  observed: number
  predicted_delta: number
  observed_delta: number
  absolute_error: number
  coverage?: number | null
  evidence_level?: string
  missing_genes?: string
  coverage_source?: string
  input_scope?: string
  score_structure_id?: string
  same_score_structure_task_count?: number
}

export interface BatchSensitivity {
  status: 'available' | 'unavailable' | 'invalid'
  reason?: string
  pooled_cells?: Record<string, number | null>
  equal_batch_weight?: Record<string, number | null>
  baseline_conclusion_consistent?: boolean | null
  baseline_comparison_reason?: string | null
  batch_key?: string
  common_batches?: string[]
  batch_counts?: Record<string, Record<string, number>>
  total_variation_control_observed?: number
  limitations?: string[]
  formula?: string
  diagnostics_sha256?: string
}

export interface MeasuredComparison {
  status: 'available' | 'unavailable' | 'preparing'
  run_id: string
  cell_line: string
  perturbation: string
  reason?: string
  available_measured_cells?: number | null
  source?: {repo?: string; revision?: string; url?: string; observed_sha256?: string; available_measured_cells?: number}
  examples: {run_id: string; cell_line: string; perturbation: string}[]
  expression?: Record<string, number | boolean | null>
  differential_expression?: Record<string, number | string | null>
  metabolic?: Record<string, number | null> | null
  parameters?: {population_counts: Record<string, number>; expression_scale: string}
  population_matching?: {input_cells: Record<string, number>; selected_cells: Record<string, number>; common_batches: string[]}
  genes?: ComparisonRow[]
  tasks?: ComparisonRow[]
  held_out_validation?: boolean
  training_exclusion_verified?: boolean
  warnings?: string[]
  warnings_zh?: string[]
  comparison_sha256?: string
  comparison_manifest_sha256?: string
  batch_sensitivity?: BatchSensitivity
  evaluation_protocol?: {status: string; reference_selection_sha256?: string | null; comparison_policy: string}
  task_coverage?: {
    finite_paired_task_count: number
    knowledge_base_task_count: number | null
    unscored_task_count: number | null
    by_evidence_level: Record<string, number>
    distinct_mean_triplets_8dp?: number
    independence_note?: string
    stratified_metrics?: Record<string, {finite_paired_task_count: number; mae: number | null; spearman: number | null}>
  }
  binding?: {prediction_manifest_sha256: string; prediction_sha256: string; code_sha256: string}
  metric_sources?: {label: string; url: string; scope: string}[]
}
