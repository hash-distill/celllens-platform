export interface CompletenessRow {
  id: string
  n_genes_all: number
  n_present_all: number
  n_missing_all: number
  fraction_present_all: number
  impact_weighted_completeness_all: number
  total_impact_missing_all: number
  missing_genes_all: string
  n_genes_essential: number
  n_present_essential: number
  n_missing_essential: number
  fraction_present_essential: number
  impact_weighted_completeness_essential: number
  missing_genes_essential: string
}

export interface CompletenessResponse {
  schema_version: 1
  run_id: string
  source_gene_sha256: string
  method: 'sccellfie.reports.compute_dataset_completeness'
  package_version: string
  implementation_sha256: string
  parameters: { metric: string; threshold: number; scope: string }
  database_version: string
  database_provenance: { manifest_sha256: string; files: Record<string, string> }
  panel_gene_count: number
  overall_summary: Record<string, number>
  tasks: CompletenessRow[]
  reactions: CompletenessRow[]
  warnings: string[]
}
