import { api } from './client'
import { apiFetch } from './http'
import { isMockEnabled } from './mockFlag'
import type { ExperimentList, ExperimentQuery } from '../types/experiment'

export async function listExperiments(query: ExperimentQuery, signal?: AbortSignal): Promise<ExperimentList> {
  if (!isMockEnabled()) return apiFetch('/experiments', {query: {...query}, signal})
  const result = await api.listRuns({...query, mode: 'online'}, signal)
  return {...result, items: result.items.map(run => ({
    id: run.run_id, source: 'online', status: run.status,
    title: `${run.request.cell_line} / ${run.request.perturbation} 扰动实验`,
    subtitle: `请求 ${run.request.n_cells} 个预测细胞`,
    created_at: run.created_at, run,
  }))}
}
