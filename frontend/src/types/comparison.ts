export interface ComparisonRow {
  id: string
  control: number
  predicted: number
  observed: number
  predicted_delta: number
  observed_delta: number
  absolute_error: number
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
  binding?: {prediction_manifest_sha256: string; prediction_sha256: string; code_sha256: string}
  metric_sources?: {label: string; url: string; scope: string}[]
}
