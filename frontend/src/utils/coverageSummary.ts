import type { CoverageCatalogue, CoverageTask } from '../types/coverage'
export type TaskCoverageFilter = 'all' | 'covered' | CoverageTask['coverage_status']
export function summarizeCoverage(data: CoverageCatalogue) {
  const tasks = { full: 0, partial: 0, absent: 0, unmapped: 0 }
  for (const task of data.tasks) tasks[task.coverage_status]++
  const reactions = { full: 0, partial: 0, absent: 0, unmapped: 0 }
  for (const reaction of data.reactions) {
    if (reaction.n_genes_all === 0) reactions.unmapped++
    else if (reaction.n_missing_all === 0) reactions.full++
    else if (reaction.n_present_all > 0) reactions.partial++
    else reactions.absent++
  }
  return { tasks, reactions, coveredGenes: data.genes.filter(gene => gene.in_panel).length,
    totalGenes: data.genes.length, totalTasks: data.tasks.length, totalReactions: data.reactions.length }
}
export function filterCoverageTasks(tasks: CoverageTask[], filter: TaskCoverageFilter, query: string) {
  const term = query.trim().toLowerCase()
  return tasks.filter(task => (filter === 'all' || (filter === 'covered'
    ? task.coverage_status === 'full' || task.coverage_status === 'partial'
    : task.coverage_status === filter)) &&
    `${task.id} ${task.label} ${task.guide?.name_zh ?? ''} ${task.guide?.name_en ?? ''} ${task.present_genes_all} ${task.missing_genes_all}`.toLowerCase().includes(term))
}
