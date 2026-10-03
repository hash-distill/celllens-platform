/**
 * 后端契约类型镜像（依据 backend/app/schemas.py 与 backend/app/api/runs.py）。
 * CSV 转 JSON 的接口（genes / 部分 reactions）原始字段为字符串，
 * 请求层统一转换为 number | null 后，组件只使用这里的已转换类型。
 */

export type CellLine = 'K562' | 'RPE1'

export type RunMode = 'online' | 'precomputed' | 'validation'

export type RunStatus =
  | 'queued'
  | 'state_running'
  | 'adapting'
  | 'metabolic_running'
  | 'validating'
  | 'completed'
  | 'failed'

export type EvidenceLevel = 'supported' | 'exploratory' | 'insufficient'

export type PointSource = 'control' | 'predicted' | 'observed'

export interface CreateRunRequest {
  cell_line: CellLine
  perturbation: string
  mode: RunMode
  n_cells: number
  seed: number
}

export interface CreateRunResponse {
  run_id: string
  status: RunStatus
  cache_hit: boolean
}

export interface RunRecord {
  run_id: string
  status: RunStatus
  stage_progress: number
  request: CreateRunRequest
  created_at: string
  updated_at: string
  warnings: string[]
  error_code: string | null
  error_message: string | null
}

export interface CoverageSummary {
  state_gene_fraction: number
  metabolic_gene_fraction: number
  reaction_fraction: number
  supported_tasks: number
  exploratory_tasks: number
  insufficient_tasks: number
}

export interface EvidenceItem {
  id: string
  label: string
  predicted_delta: number
  observed_delta: number | null
  coverage: number
  evidence_level: EvidenceLevel
  determinant_genes: string[]
}

export interface RunSummary {
  run_id: string
  status: RunStatus
  stage_progress: number
  cell_line: string
  perturbation: string
  coverage: CoverageSummary | null
  top_genes: EvidenceItem[]
  metabolic_tasks: EvidenceItem[]
  warnings: string[]
  error_code: string | null
}

export interface ContextItem {
  cell_line: string
  online_ready: boolean
  validation_ready: boolean
  precomputed_ready: boolean
  model_id: string | null
  disabled_reason: string | null
  readiness_reasons: string[]
}

export interface PerturbationList {
  cell_line: string
  items: string[]
}

export interface HealthResponse {
  service: string
  status: string
  database: string
}

export interface ReadyChecks {
  database: boolean
  worker: boolean
  gpu: boolean
}

export interface ReadyResponse {
  ready: boolean
  checks: ReadyChecks
}

export interface ProjectionPoint {
  x: number
  y: number
  source: PointSource
  cell_index: number
}

export interface ProjectionResponse {
  method: string
  seed: number
  points: ProjectionPoint[]
}

/** genes 接口行（请求层已完成字符串 → 数值转换；空串/null/非有限为 null） */
export interface GeneRow {
  gene: string
  control: number | null
  predicted: number | null
  predicted_delta: number | null
  observed: number | null
  observed_delta: number | null
}

export interface GenesResponse {
  items: GeneRow[]
  limit: number
  truncated: boolean
}

export interface MetabolicTasksResponse {
  items: EvidenceItem[]
  limit: number
  truncated: boolean
  scope?: 'top' | 'all'
  total?: number
  excluded_count?: number
}

export interface RunProvenance {
  run_id: string
  source_type: 'online' | 'validation' | 'synthetic_precomputed'
  created_at: string
  completed_at: string
  manifest_sha256: string
  code_sha256: string | null
  source_manifest_sha256: string | null
  assets: Record<string, string | null>
}

export interface RunValidation {
  run_id: string
  metrics: Record<string, number | null>
  protocol_status: 'unconfirmed'
  warnings: string[]
}

export interface ReactionRow {
  reaction: string
  control: number | null
  predicted: number | null
  predicted_delta: number | null
}

export interface ReactionsResponse {
  items: ReactionRow[]
  limit: number
  truncated: boolean
}
