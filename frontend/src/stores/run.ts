import { defineStore } from 'pinia'
import { api } from '../api/client'
import { ApiError } from '../api/http'
import { useServiceStore } from './service'
import { useRecentStore } from './recent'
import type {
  CreateRunRequest,
  CreateRunResponse,
  GenesResponse,
  MetabolicTasksResponse,
  ProjectionResponse,
  ReactionsResponse,
  RunRecord,
  RunProvenance,
  RunValidation,
  RunSummary,
} from '../types/run'

export type BlockStatus = 'idle' | 'loading' | 'ok' | 'error'

export interface AsyncBlock<T> {
  status: BlockStatus
  data: T | null
  error: ApiError | null
}

export type BlockKind = 'summary' | 'projection' | 'genes' | 'tasks' | 'reactions' | 'provenance' | 'validation'

export interface RunEntry {
  runId: string
  record: RunRecord | null
  recordError: ApiError | null
  notFound: boolean
  polling: boolean
  /** 轮询期间的临时问题说明（如网络重试中），不改变运行状态 */
  pollIssue: string | null
  summary: AsyncBlock<RunSummary>
  projection: AsyncBlock<ProjectionResponse>
  genes: AsyncBlock<GenesResponse>
  tasks: AsyncBlock<MetabolicTasksResponse>
  reactions: AsyncBlock<ReactionsResponse>
  provenance: AsyncBlock<RunProvenance>
  validation: AsyncBlock<RunValidation>
}

interface Poller {
  controller: AbortController
  timer: number | null
  stopped: boolean
  failCount: number
  inFlight: boolean
}

function emptyBlock<T>(): AsyncBlock<T> {
  return { status: 'idle', data: null, error: null }
}

function newEntry(runId: string): RunEntry {
  return {
    runId,
    record: null,
    recordError: null,
    notFound: false,
    polling: false,
    pollIssue: null,
    summary: emptyBlock<RunSummary>(),
    projection: emptyBlock<ProjectionResponse>(),
    genes: emptyBlock<GenesResponse>(),
    tasks: emptyBlock<MetabolicTasksResponse>(),
    reactions: emptyBlock<ReactionsResponse>(),
    provenance: emptyBlock<RunProvenance>(),
    validation: emptyBlock<RunValidation>(),
  }
}

const POLL_INTERVAL_VISIBLE = 2000
const POLL_INTERVAL_HIDDEN = 8000
/** 短暂网络失败退避：2 / 4 / 8 / 15 秒，之后保持 15 秒 */
const BACKOFF_MS = [2000, 4000, 8000, 15000]

const pollers = new Map<string, Poller>()
const blockControllers = new WeakMap<object, Map<BlockKind, AbortController>>()

function pollInterval(): number {
  return document.visibilityState === 'hidden' ? POLL_INTERVAL_HIDDEN : POLL_INTERVAL_VISIBLE
}

export const useRunStore = defineStore('run', {
  state: () => ({
    entries: {} as Record<string, RunEntry>,
    currentRunId: null as string | null,
    submitting: false,
    submitError: null as ApiError | null,
    /** 提交超时：服务端可能已接收，保留参数等待用户确认，不自动重发 */
    submitTimeoutPending: null as CreateRunRequest | null,
  }),
  getters: {
    entry(state) {
      return (runId: string): RunEntry | null => state.entries[runId] ?? null
    },
    currentEntry(state): RunEntry | null {
      return state.currentRunId ? (state.entries[state.currentRunId] ?? null) : null
    },
  },
  actions: {
    ensureEntry(runId: string): RunEntry {
      if (!this.entries[runId]) this.entries[runId] = newEntry(runId)
      return this.entries[runId]
    },

    /**
     * 打开运行：切换运行时终止旧轮询（AbortController + run_id 校验），
     * 刷新后按 URL 中的 run_id 恢复状态。
     */
    openRun(runId: string): void {
      if (this.currentRunId && this.currentRunId !== runId) {
        this.stopPolling(this.currentRunId)
        this.cancelResults(this.currentRunId)
      }
      this.currentRunId = runId
      const entry = this.ensureEntry(runId)
      entry.notFound = false
      const status = entry.record?.status
      if (status === 'completed' || status === 'failed') {
        if (status === 'completed' && entry.provenance.status === 'idle') void this.loadProvenance(runId)
        // 已终结的运行无需轮询；确保汇总可用
        if (status === 'completed' && entry.summary.status === 'idle') {
          void this.loadSummary(runId)
        }
        return
      }
      this.startPolling(runId)
    },

    leaveRun(): void {
      if (this.currentRunId) {
        this.stopPolling(this.currentRunId)
        this.cancelResults(this.currentRunId)
      }
      this.currentRunId = null
    },

    startPolling(runId: string): void {
      if (pollers.get(runId) && !pollers.get(runId)!.stopped) return
      this.stopPolling(runId)
      const poller: Poller = {
        controller: new AbortController(),
        timer: null,
        stopped: false,
        failCount: 0,
        inFlight: false,
      }
      pollers.set(runId, poller)
      void this.pollCycle(runId, poller)
    },

    cancelResults(runId: string): void {
      const entry = this.entries[runId]
      if (!entry) return
      blockControllers.get(entry)?.forEach((controller) => controller.abort())
      for (const kind of ['summary', 'projection', 'genes', 'tasks', 'reactions', 'provenance', 'validation'] as const) {
        if (entry[kind].status === 'loading') entry[kind].status = 'idle'
      }
    },

    stopPolling(runId: string): void {
      const poller = pollers.get(runId)
      if (!poller) return
      poller.stopped = true
      poller.controller.abort()
      if (poller.timer !== null) window.clearTimeout(poller.timer)
      pollers.delete(runId)
      const entry = this.entries[runId]
      if (entry) entry.polling = false
    },

    schedule(runId: string, poller: Poller, delay: number): void {
      if (poller.stopped) return
      if (poller.timer !== null) window.clearTimeout(poller.timer)
      poller.timer = window.setTimeout(() => {
        poller.timer = null
        void this.pollCycle(runId, poller)
      }, delay)
    },

    /** 串行轮询：前一次结束后再发下一次 */
    async pollCycle(runId: string, poller: Poller): Promise<void> {
      if (poller.stopped || poller.inFlight || this.currentRunId !== runId) return
      poller.inFlight = true
      const entry = this.ensureEntry(runId)
      entry.polling = true
      const service = useServiceStore()
      try {
        const record = await api.getRun(runId, poller.controller.signal)
        // run_id 校验：已切换或已停止的旧响应直接丢弃
        if (poller.stopped || this.currentRunId !== runId) return
        entry.record = record
        entry.recordError = null
        entry.pollIssue = null
        poller.failCount = 0
        useRecentStore().updateStatus(runId, record.status)

        if (record.status === 'completed' || record.status === 'failed') {
          entry.polling = false
          pollers.delete(runId)
          if (record.status === 'completed') {
            void this.loadSummary(runId)
            void this.loadProvenance(runId)
          }
          return
        }
        this.schedule(runId, poller, pollInterval())
      } catch (err) {
        if (poller.stopped || this.currentRunId !== runId) return
        if (!(err instanceof ApiError) || err.kind === 'abort') return
        if (err.status === 404) {
          entry.notFound = true
          entry.recordError = err
          entry.polling = false
          pollers.delete(runId)
          return
        }
        if (err.kind === 'network' || err.kind === 'timeout') {
          // 网络中断不改写任务状态，按 2/4/8/15s 退避，恢复后继续
          poller.failCount += 1
          const delay = BACKOFF_MS[Math.min(poller.failCount - 1, BACKOFF_MS.length - 1)]
          entry.pollIssue = '连接异常或读取超时，正在自动重试（已有结果与任务状态保持不变）…'
          service.markNetworkIssue()
          this.schedule(runId, poller, delay)
          return
        }
        // 其他 HTTP 错误：保留错误信息，降频继续观察
        entry.recordError = err
        this.schedule(runId, poller, pollInterval() * 3)
      } finally {
        poller.inFlight = false
      }
    },

    /** 页面恢复可见时立即补一次轮询 */
    wakePolling(): void {
      const runId = this.currentRunId
      if (!runId) return
      const poller = pollers.get(runId)
      if (poller && !poller.stopped && !poller.inFlight) {
        if (poller.timer !== null) {
          window.clearTimeout(poller.timer)
          poller.timer = null
        }
        void this.pollCycle(runId, poller)
      }
    },

    // ---------- 结果块加载（局部失败不清空整页，可局部重试） ----------

    blockController(entry: RunEntry, kind: BlockKind): AbortController {
      let map = blockControllers.get(entry)
      if (!map) {
        map = new Map()
        blockControllers.set(entry, map)
      }
      map.get(kind)?.abort()
      const controller = new AbortController()
      map.set(kind, controller)
      return controller
    },

    async loadSummary(runId: string): Promise<void> {
      const entry = this.ensureEntry(runId)
      if (entry.summary.status === 'loading') return
      const controller = this.blockController(entry, 'summary')
      entry.summary = { status: 'loading', data: entry.summary.data, error: null }
      try {
        const data = await api.getSummary(runId, controller.signal)
        entry.summary = { status: 'ok', data, error: null }
      } catch (err) {
        if (err instanceof ApiError && err.kind === 'abort') return
        entry.summary = {
          status: 'error',
          data: null,
          error: err instanceof ApiError ? err : null,
        }
      }
    },

    async loadProvenance(runId: string): Promise<void> {
      const entry = this.ensureEntry(runId)
      if (entry.provenance.status === 'loading') return
      const controller = this.blockController(entry, 'provenance')
      entry.provenance = { status:'loading', data:entry.provenance.data, error:null }
      try {
        const data = await api.getProvenance(runId, controller.signal)
        if (!controller.signal.aborted) entry.provenance = { status:'ok', data, error:null }
      } catch (error) {
        if (controller.signal.aborted) return
        entry.provenance = { status:'error', data:null, error:error instanceof ApiError ? error : null }
      }
    },

    async loadValidation(runId: string): Promise<void> {
      const entry = this.ensureEntry(runId)
      if (entry.validation.status === 'loading') return
      const controller = this.blockController(entry, 'validation')
      entry.validation = { status:'loading', data:entry.validation.data, error:null }
      try {
        const data = await api.getValidation(runId, controller.signal)
        if (!controller.signal.aborted) entry.validation = { status:'ok', data, error:null }
      } catch (error) {
        if (controller.signal.aborted) return
        entry.validation = { status:'error', data:null, error:error instanceof ApiError ? error : null }
      }
    },

    async loadProjection(runId: string): Promise<void> {
      const entry = this.ensureEntry(runId)
      if (entry.projection.status === 'loading') return
      const controller = this.blockController(entry, 'projection')
      entry.projection = { status: 'loading', data: entry.projection.data, error: null }
      try {
        const data = await api.getProjection(runId, controller.signal)
        entry.projection = { status: 'ok', data, error: null }
      } catch (err) {
        if (err instanceof ApiError && err.kind === 'abort') return
        entry.projection = {
          status: 'error',
          data: null,
          error: err instanceof ApiError ? err : null,
        }
      }
    },

    async loadGenes(runId: string): Promise<void> {
      const entry = this.ensureEntry(runId)
      if (entry.genes.status === 'loading') return
      const controller = this.blockController(entry, 'genes')
      entry.genes = { status: 'loading', data: entry.genes.data, error: null }
      try {
        const data = await api.getGenes(runId, 2000, controller.signal)
        entry.genes = { status: 'ok', data, error: null }
      } catch (err) {
        if (err instanceof ApiError && err.kind === 'abort') return
        entry.genes = { status: 'error', data: null, error: err instanceof ApiError ? err : null }
      }
    },

    async loadTasks(runId: string): Promise<void> {
      const entry = this.ensureEntry(runId)
      if (entry.tasks.status === 'loading') return
      const controller = this.blockController(entry, 'tasks')
      entry.tasks = { status: 'loading', data: entry.tasks.data, error: null }
      try {
        const data = await api.getMetabolicTasks(runId, 1000, controller.signal)
        entry.tasks = { status: 'ok', data, error: null }
      } catch (err) {
        if (err instanceof ApiError && err.kind === 'abort') return
        entry.tasks = { status: 'error', data: null, error: err instanceof ApiError ? err : null }
      }
    },

    async loadReactions(runId: string): Promise<void> {
      const entry = this.ensureEntry(runId)
      if (entry.reactions.status === 'loading') return
      if (entry.tasks.data?.reactions_available === false) {
        entry.reactions = { status: 'ok', data: { items: [], limit: 1000, truncated: false }, error: null }
        return
      }
      const controller = this.blockController(entry, 'reactions')
      entry.reactions = { status: 'loading', data: entry.reactions.data, error: null }
      try {
        const data = await api.getReactions(runId, 1000, controller.signal)
        entry.reactions = { status: 'ok', data, error: null }
      } catch (err) {
        if (err instanceof ApiError && err.kind === 'abort') return
        entry.reactions = {
          status: 'error',
          data: null,
          error: err instanceof ApiError ? err : null,
        }
      }
    },

    retryBlock(runId: string, kind: BlockKind): void {
      switch (kind) {
        case 'provenance':
          void this.loadProvenance(runId)
          break
        case 'validation':
          void this.loadValidation(runId)
          break
        case 'summary':
          void this.loadSummary(runId)
          break
        case 'projection':
          void this.loadProjection(runId)
          break
        case 'genes':
          void this.loadGenes(runId)
          break
        case 'tasks':
          void this.loadTasks(runId)
          break
        case 'reactions':
          void this.loadReactions(runId)
          break
      }
    },

    /** 标签页激活时按需加载（仅在运行完成后读取产物） */
    ensureTabData(runId: string, tab: string): void {
      const entry = this.ensureEntry(runId)
      if (entry.record?.status !== 'completed') return
      if (entry.summary.status === 'idle') void this.loadSummary(runId)
      switch (tab) {
        case 'cell':
          if (entry.projection.status === 'idle') void this.loadProjection(runId)
          break
        case 'genes':
          if (entry.genes.status === 'idle') void this.loadGenes(runId)
          break
        case 'metabolism':
          if (entry.tasks.status === 'idle') {
            void this.loadTasks(runId).then(() => {
              if (entry.tasks.status === 'ok' && entry.reactions.status === 'idle') void this.loadReactions(runId)
            })
          } else if (entry.tasks.status === 'ok' && entry.reactions.status === 'idle') {
            void this.loadReactions(runId)
          }
          break
        case 'validation':
          if (entry.validation.status === 'idle') void this.loadValidation(runId)
          if (entry.genes.status === 'idle') void this.loadGenes(runId)
          if (entry.tasks.status === 'idle') void this.loadTasks(runId)
          break
      }
    },

    /** 强制重新读取运行记录（手动刷新） */
    async refreshRecord(runId: string): Promise<void> {
      const entry = this.ensureEntry(runId)
      try {
        const record = await api.getRun(runId)
        entry.record = record
        entry.recordError = null
        entry.notFound = false
        useRecentStore().updateStatus(runId, record.status)
        if (record.status === 'completed' && entry.summary.status === 'idle') {
          void this.loadSummary(runId)
        }
      } catch (err) {
        if (err instanceof ApiError) {
          if (err.status === 404) entry.notFound = true
          entry.recordError = err
        }
      }
    },

    // ---------- 提交 ----------

    /**
     * 创建任务。成功返回 202 响应（仅表示已接收）。
     * 超时 / 网络失败不自动重发：超时进入「提交结果待确认」，由用户确认后再操作。
     */
    async createRun(payload: CreateRunRequest): Promise<CreateRunResponse | null> {
      if (this.submitting) return null
      this.submitting = true
      this.submitError = null
      this.submitTimeoutPending = null
      try {
        const res = await api.createRun(payload)
        useRecentStore().add({
          run_id: res.run_id,
          cell_line: payload.cell_line,
          perturbation: payload.perturbation,
          mode: payload.mode,
          status: res.status,
        })
        return res
      } catch (err) {
        if (err instanceof ApiError) {
          if (err.kind === 'timeout') {
            this.submitTimeoutPending = { ...payload }
          } else if (err.kind === 'network') {
            useServiceStore().markNetworkIssue()
            this.submitError = err
          } else {
            this.submitError = err
          }
        }
        return null
      } finally {
        this.submitting = false
      }
    },

    clearSubmitState(): void {
      this.submitError = null
      this.submitTimeoutPending = null
    },
  },
})
