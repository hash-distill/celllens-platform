export interface GeneCategory {
  id: string
  name_zh: string
  name_en: string
  description_zh: string
  description_en: string
  count: number
}
export interface GeneAnnotation {
  symbol: string
  approved_symbol: string
  hgnc_id: string | null
  name_en: string
  name_zh?: string | null
  category_ids: string[]
  protein_classes: {id: string; name_en: string}[]
  uniprot_ids: string[]
}
export interface ClassificationInfo {
  available: boolean
  method: string
  multi_label: boolean
  warning?: string | null
  provenance: {annotation_version: string; source_url: string; files: Record<string, string>} | null
}
export interface TaskGuide {
  name_zh: string
  name_en: string
  description_zh: string
  description_en: string
  scope_zh: string
  scope_en: string
  source_url: string
  source_label: string
}
