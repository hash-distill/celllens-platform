import type { PointSource } from './run'

export interface CellDistribution {
  n: number; n_valid: number; n_displayed: number
  mean: number | null; q25: number | null; median: number | null; q75: number | null
  ecdf: number[][]
}
export interface ScientificCellState {
  run_id: string; cell_line: string; perturbation: string
  method: string; gene_count: number; explained_variance_ratio: number[]
  embedding_space?: 'expression' | 'metabolic'
  embedding_preprocessing?: { feature_count: number; feature_ids: string[]; input_units: string; scaling: string; missing_policy: string }
  embedding_parameters?: { n_neighbors: number; min_dist: number; random_state: number; fit_sources: string[]; preprocessing: { n_components: number } } | null
  feature: { kind: 'gene' | 'task'; id: string; units: string }
  available_features: { genes: string[]; tasks: string[] }
  points: { x: number; y: number; source: PointSource; cell_id: string; cell_index: number; value: number | null }[]
  distributions: Partial<Record<PointSource, CellDistribution>>
  total_cells: number; displayed_cells: number
  provenance: { manifest_sha256: string; source_run_id: string; gene_means_verified: boolean; task_cell_ids_verified: boolean }
  bounds: number[][]; color_range: number[]; limitations: string[]
}
