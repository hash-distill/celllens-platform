import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { api } from '../api/client'
import type { EvidenceItem } from '../types/run'
import { predictionTrace } from './predictionEvidence'

export interface TaskAssociation {
  status: 'loading' | 'ok' | 'error' | 'unavailable'
  genes: string[]
  error?: string
}

/** Only associations with saved task, reaction and gene prediction changes. */
export function useTaskAssociations(runId: () => string, rows: Ref<EvidenceItem[]>) {
  const associations = ref<Record<string, TaskAssociation>>({})
  let controller: AbortController | undefined, currentRun = ''
  async function load() {
    controller?.abort()
    const active = controller = new AbortController(), id = runId()
    if (id !== currentRun) { associations.value = {}; currentRun = id }
    const pending = rows.value.filter(row => {
      if (row.trace_available === false) {
        associations.value[row.id] = {status:'unavailable',genes:[]}
        return false
      }
      return associations.value[row.id]?.status !== 'ok'
    })
    pending.forEach(row => { associations.value[row.id] = {status:'loading',genes:[]} })
    let index = 0
    await Promise.all(Array.from({length:Math.min(4,pending.length)}, async () => {
      while (index < pending.length && !active.signal.aborted) {
        const row = pending[index++]!
        try {
          const trace = await api.getFunctionTrace(id,row.id,active.signal)
          if (active.signal.aborted) return
          if (trace.run_id !== id || trace.task.id !== row.id || trace.truncated || trace.reactions.some(reaction => reaction.truncated)) throw new Error('关联记录不完整或与本次任务不符')
          associations.value[row.id] = {
            status:'ok',
            genes:[...new Set(predictionTrace(trace)?.reactions.flatMap(reaction => reaction.genes.map(gene => gene.id)) ?? [])].sort(),
          }
        } catch (error) {
          if (!active.signal.aborted) associations.value[row.id] = {
            status:'error',genes:[],error:error instanceof Error ? error.message : '关联读取失败',
          }
        }
      }
    }))
  }
  watch(() => [runId(),rows.value.map(row => `${row.id}:${row.trace_available}`).join('|')], () => {void load()}, {immediate:true})
  onBeforeUnmount(() => controller?.abort())
  return {associations,retry:load}
}
