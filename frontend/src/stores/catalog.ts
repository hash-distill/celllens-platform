import { defineStore } from 'pinia'
import { api } from '../api/client'
import { ApiError } from '../api/http'
import type { ContextItem, RunMode } from '../types/run'

interface PerturbationState {
  items: string[]
  loading: boolean
  error: ApiError | null
}

export const useCatalogStore = defineStore('catalog', {
  state: () => ({
    contexts: [] as ContextItem[],
    loading: false,
    error: null as ApiError | null,
    perturbations: {} as Record<string, PerturbationState>,
  }),
  getters: {
    contextFor(state) {
      return (cellLine: string): ContextItem | null =>
        state.contexts.find((c) => c.cell_line === cellLine) ?? null
    },
  },
  actions: {
    async load(): Promise<void> {
      this.loading = true
      this.error = null
      try {
        this.contexts = await api.contexts()
      } catch (err) {
        this.error = err instanceof ApiError ? err : new ApiError({
          kind: 'network',
          status: null,
          code: null,
          message: String(err),
          endpoint: '/catalog/contexts',
        })
        this.contexts = []
      } finally {
        this.loading = false
      }
    },
    async loadPerturbations(cellLine: string, mode: RunMode = 'online', force = false): Promise<void> {
      const key = `${cellLine}:${mode}`
      const existing = this.perturbations[key]
      if (!force && existing && (existing.loading || existing.items.length > 0)) return
      this.perturbations[key] = { items: [], loading: true, error: null }
      try {
        const res = await api.perturbations(cellLine, mode)
        this.perturbations[key] = { items: res.items, loading: false, error: null }
      } catch (err) {
        this.perturbations[key] = {
          items: [],
          loading: false,
          error: err instanceof ApiError ? err : null,
        }
      }
    },
  },
})
