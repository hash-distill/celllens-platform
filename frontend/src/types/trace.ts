export interface TraceScore {
  id: string
  label: string
  control: number | null
  predicted: number | null
  predicted_delta: number | null
  observed_delta?: number | null
}
export interface TaskTraceResponse {
  schema_version: number
  scope?: 'top' | 'all'
  run_id: string
  database_version: string
  database_provenance: { manifest_sha256: string; files: Record<string, string> }
  task: TraceScore & { category: string | null; subcategory?: string | null; observed_delta: number | null; coverage: number; evidence_level: string }
  reactions: Array<TraceScore & { gene_rule?: string | null; genes: TraceScore[]; total_genes: number; truncated: boolean }>
  score_units?: Record<string, string>
  relationship_kind: 'knowledge_association'
  determinant_genes: string[]
  determinant_status: 'unavailable'
  total_reactions: number
  truncated: boolean
  warnings: string[]
}
