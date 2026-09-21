export type RunStatus =
  | 'queued'
  | 'state_running'
  | 'adapting'
  | 'metabolic_running'
  | 'validating'
  | 'completed'
  | 'failed'

export interface CreateRunRequest {
  cell_line: 'K562' | 'RPE1'
  perturbation: string
  mode: 'online' | 'precomputed' | 'validation'
  n_cells: number
  seed: number
}

export interface CoverageSummary {
  state_gene_fraction: number
  metabolic_gene_fraction: number
  reaction_fraction: number
  supported_tasks: number
  exploratory_tasks: number
  insufficient_tasks: number
}

export interface RunSummary {
  run_id: string
  status: RunStatus
  stage_progress: number
  cell_line: string
  perturbation: string
  coverage: CoverageSummary | null
  warnings: string[]
  error_code: string | null
}

