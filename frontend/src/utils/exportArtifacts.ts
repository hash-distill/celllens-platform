import type { TaskTraceResponse } from '../types/trace'
import type { CoverageCatalogue } from '../types/coverage'

function traceCounts(trace: TaskTraceResponse | null) {
  const reactions = trace?.reactions ?? []
  return {
    reactions: reactions.length,
    gene_associations: reactions.reduce((count, reaction) => count + reaction.genes.length, 0),
    unique_genes: new Set(reactions.flatMap(reaction => reaction.genes.map(gene => gene.id))).size,
  }
}

/** The API document remains the export fact source; display metadata never rewrites it. */
export function buildTraceExport(raw: TaskTraceResponse, displayed: TaskTraceResponse | null, selection: {selected_reaction: string; embedding: string; space: string}) {
  return {
    ...raw,
    display: {
      ...selection,
      filter: 'complete-finite-nonzero-prediction',
      source_counts: traceCounts(raw),
      displayed_counts: traceCounts(displayed),
      displayed_reaction_ids: (displayed?.reactions ?? []).map(reaction => reaction.id),
      displayed_gene_ids: [...new Set((displayed?.reactions ?? []).flatMap(reaction => reaction.genes.map(gene => gene.id)))],
      observed_mean: 'control + saved observed_delta',
    },
  }
}

/** Coverage is a catalogue; include all source reaction rows so partial references resolve. */
export function buildCoverageExport(data: CoverageCatalogue) {
  const genes = data.genes.filter(gene => gene.in_panel)
  const tasks = data.tasks.filter(task => task.n_present_all > 0 && (task.coverage_status === 'full' || task.coverage_status === 'partial'))
  const reactions = data.reactions
  const reactionIds = new Set(reactions.map(reaction => reaction.id)), taskIds = new Set(tasks.map(task => task.id))
  const referencedReactions = [...new Set(genes.flatMap(gene => gene.reactions))]
  const referencedTasks = [...new Set(genes.flatMap(gene => gene.tasks))]
  const fullReactions = reactions.filter(reaction => reaction.n_genes_all > 0 && reaction.n_missing_all === 0).length
  const partialReactions = reactions.filter(reaction => reaction.n_present_all > 0 && reaction.n_missing_all > 0).length
  const fullTasks = tasks.filter(task => task.coverage_status === 'full').length
  return {
    ...data,
    export_schema: 'celllens.coverage-catalogue.v2',
    inclusion_policy: {
      genes: 'in_panel=true; independent of page search/category/pagination',
      tasks: 'n_present_all>0 and coverage_status in [full,partial]; independent of page filters',
      reactions: 'all source reaction completeness rows, including partial and absent coverage',
      references: 'gene reaction/task IDs resolve in exported arrays or omitted_references; source catalogue has no task-to-reaction edge list',
      interpretation: 'coverage catalogue, not a stoichiometric model or measured metabolic flux',
    },
    source_counts: {genes:data.genes.length,tasks:data.tasks.length,reactions:data.reactions.length},
    exported_counts: {genes:genes.length,tasks:tasks.length,reactions:reactions.length},
    covered_counts: {genes:genes.length,fully_covered_tasks:fullTasks,fully_covered_reactions:fullReactions},
    task_counts: {fully_covered:fullTasks,partially_covered:tasks.length-fullTasks,exported:tasks.length},
    reaction_counts: {fully_covered:fullReactions,partially_covered:partialReactions,exported:reactions.length},
    omitted_references: {
      reactions: referencedReactions.filter(id => !reactionIds.has(id)).map(id => ({id,reason:'not present in source catalogue reaction rows'})),
      tasks: referencedTasks.filter(id => !taskIds.has(id)).map(id => ({id,reason:'outside covered/partially covered task inclusion policy or absent from source catalogue'})),
    },
    genes, tasks, reactions,
  }
}
