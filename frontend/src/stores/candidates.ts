import { defineStore } from 'pinia'
import type { CreateRunRequest } from '../types/run'
import { historyKey, readHistory } from '../utils/storage'

export interface CandidateItem {
  run_id: string
  request: CreateRunRequest
  added_at: string
}

const STORAGE_KEY = 'celllens.candidates.v1'
export const MAX_CANDIDATES = 4

function loadFromStorage(): CandidateItem[] {
  return readHistory<CandidateItem>(STORAGE_KEY).slice(0, MAX_CANDIDATES)
}

/** 候选托盘：以 run_id 去重、最多 4 个，存储在本机（本浏览器记录） */
export const useCandidatesStore = defineStore('candidates', {
  state: () => ({
    items: loadFromStorage(),
    expanded: false,
  }),
  getters: {
    isFull(state): boolean {
      return state.items.length >= MAX_CANDIDATES
    },
    has(state) {
      return (runId: string): boolean => state.items.some((i) => i.run_id === runId)
    },
  },
  actions: {
    persist(): void {
      try {
        localStorage.setItem(historyKey(STORAGE_KEY), JSON.stringify(this.items))
      } catch {
        // 本地存储不可用时静默忽略
      }
    },
    /** 返回添加结果，失败原因用于禁用提示 */
    add(runId: string, request: CreateRunRequest): { ok: boolean; reason: string | null } {
      if (this.has(runId)) return { ok: false, reason: '该运行已在候选托盘中' }
      if (this.isFull) return { ok: false, reason: '候选托盘最多保存 4 个运行，请先移除' }
      this.items = [
        ...this.items,
        { run_id: runId, request: { ...request }, added_at: new Date().toISOString() },
      ]
      this.persist()
      return { ok: true, reason: null }
    },
    remove(runId: string): void {
      this.items = this.items.filter((i) => i.run_id !== runId)
      this.persist()
    },
    clear(): void {
      this.items = []
      this.persist()
    },
    toggleExpanded(): void {
      this.expanded = !this.expanded
    },
  },
})
