import type { CompletenessResponse, CompletenessRow } from './completeness'
import type { ClassificationInfo, GeneAnnotation, GeneCategory, TaskGuide } from './geneEducation'

export interface CoverageGene extends GeneAnnotation {
  symbol: string
  approved_symbol: string
  hgnc_id: string | null
  in_panel: boolean
  tasks: string[]
  reactions: string[]
}
export interface CoverageTask extends CompletenessRow {
  label: string
  category: string | null
  subcategory: string | null
  coverage_status: 'full' | 'partial' | 'absent' | 'unmapped'
  present_genes_all: string
  guide: TaskGuide | null
}
export interface CoverageCatalogue extends Omit<CompletenessResponse, 'run_id' | 'source_gene_sha256' | 'tasks'> {
  source: {kind: 'model' | 'run'; id: string; title: string; cell_line?: string; model_id?: string; panel_sha256: string}
  models: {id: string; cell_line: string}[]
  genes: CoverageGene[]
  tasks: CoverageTask[]
  gene_categories: GeneCategory[]
  classification: ClassificationInfo
}
