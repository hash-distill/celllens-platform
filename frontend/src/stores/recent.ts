import { defineStore } from 'pinia'
import type { RunMode, RunStatus } from '../types/run'
import { historyKey, readHistory } from '../utils/storage'

export interface RecentRunItem {
  run_id: string
  cell_line: string
  perturbation: string
  mode: RunMode
  status: RunStatus | null
  opened_at: string
}

const STORAGE_KEY = 'celllens.recentRuns.v1'
const MAX_ITEMS = 12

function loadFromStorage(): RecentRunItem[] {
  return readHistory<RecentRunItem>(STORAGE_KEY).slice(0, MAX_ITEMS)
}

/** 最近运行：只记录本浏览器创建或打开过的任务（本浏览器记录，不代表服务器历史） */
export const useRecentStore = defineStore('recent', {
  state: () => ({
    items: loadFromStorage(),
  }),
  actions: {
    persist(): void {
      try {
        localStorage.setItem(historyKey(STORAGE_KEY), JSON.stringify(this.items))
      } catch {
        // 本地存储不可用时静默忽略（功能降级为仅会话内）
      }
    },
    add(item: Omit<RecentRunItem, 'opened_at'>): void {
      const entry: RecentRunItem = { ...item, opened_at: new Date().toISOString() }
      this.items = [entry, ...this.items.filter((i) => i.run_id !== entry.run_id)].slice(0, MAX_ITEMS)
      this.persist()
    },
    updateStatus(runId: string, status: RunStatus): void {
      const target = this.items.find((i) => i.run_id === runId)
      if (target && target.status !== status) {
        target.status = status
        this.persist()
      }
    },
    remove(runId: string): void {
      this.items = this.items.filter((i) => i.run_id !== runId)
      this.persist()
    },
    clear(): void {
      this.items = []
      this.persist()
    },
  },
})
