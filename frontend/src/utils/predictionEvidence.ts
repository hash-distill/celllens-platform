import type { TaskTraceResponse } from '../types/trace'

export interface PredictionValues {
  control?: number | null
  predicted?: number | null
  predicted_delta?: number | null
}

/** A recorded numeric prediction change, never a significance or causal claim. */
export function hasPredictionChange(row: PredictionValues): boolean {
  return [row.control,row.predicted,row.predicted_delta].every(value => typeof value === 'number' && Number.isFinite(value)) && row.predicted_delta !== 0
}

/** Derive a display document without changing the frozen scientific artifact. */
export function predictionTrace(trace: TaskTraceResponse): TaskTraceResponse | null {
  if (!hasPredictionChange(trace.task)) return null
  const reactions = trace.reactions.filter(hasPredictionChange).map(reaction => {
    const genes = reaction.genes.filter(hasPredictionChange)
    return {...reaction,genes,total_genes:genes.length,gene_rule:null}
  }).filter(reaction => reaction.genes.length > 0)
  return {...trace,reactions,total_reactions:reactions.length,determinant_genes:[]}
}
