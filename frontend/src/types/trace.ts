export interface TraceScore {
  id: string
  label: string
  control: number | null
  predicted: number | null
  predicted_delta: number | null
}
export interface TaskTraceResponse {
  schema_version: number
  run_id: string
  database_version: string
  database_provenance: { manifest_sha256: string; files: Record<string, string> }
  task: TraceScore & { category: string | null; observed_delta: number | null; coverage: number; evidence_level: string }
  reactions: Array<TraceScore & { genes: TraceScore[]; total_genes: number; truncated: boolean }>
  relationship_kind: 'knowledge_association'
  determinant_genes: string[]
  determinant_status: 'unavailable'
  total_reactions: number
  truncated: boolean
  warnings: string[]
}
