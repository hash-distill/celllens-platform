import translations from '../../../backend/app/resources/biology_zh.json'

// The API and bundled charts use the same display dictionary. Scientific IDs,
// saved scores and the frozen HGNC/PANTHER/scCellFie snapshots stay unchanged.
const taskNames: Record<string, string> = translations.task_names
const groupNames: Record<string, string> = translations.groups

export function taskName(id: string, fallback?: string | null): string {
  return taskNames[id] ?? (fallback ? taskNames[fallback] ?? fallback : id)
}

export function metabolicGroupName(value?: string | null): string {
  return value ? groupNames[value] ?? value : '未提供功能分类'
}
