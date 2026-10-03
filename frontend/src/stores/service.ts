import { defineStore } from 'pinia'
import { api } from '../api/client'
import { ApiError } from '../api/http'
import type { HealthResponse, ReadyChecks } from '../types/run'

export type ServiceLevel = 'unknown' | 'ok' | 'degraded' | 'down'

interface ServiceState {
  health: HealthResponse | null
  /** health HTTP 200 之外，还需 status / database 字段同时正常才算 true */
  healthFieldsOk: boolean | null
  readyHttpStatus: number | null
  ready: boolean | null
  checks: ReadyChecks | null
  lastCheckedAt: string | null
  checking: boolean
  /** 最近一次健康检查是否为网络级失败（驱动顶部连接异常提示条） */
  networkDown: boolean
}

function healthFieldsOk(body: HealthResponse | null): boolean {
  if (!body) return false
  const status = String(body.status ?? '').toLowerCase()
  const database = String(body.database ?? '').toLowerCase()
  const okWords = new Set(['ok', 'healthy', 'up', 'connected', 'ready', 'true'])
  return okWords.has(status) && okWords.has(database)
}

export const useServiceStore = defineStore('service', {
  state: (): ServiceState => ({
    health: null,
    healthFieldsOk: null,
    readyHttpStatus: null,
    ready: null,
    checks: null,
    lastCheckedAt: null,
    checking: false,
    networkDown: false,
  }),
  getters: {
    level(state): ServiceLevel {
      if (state.networkDown) return 'down'
      if (state.health === null && state.lastCheckedAt === null) return 'unknown'
      if (state.healthFieldsOk === false) return 'degraded'
      if (state.ready === false) return 'degraded'
      if (state.healthFieldsOk === true && state.ready === true) return 'ok'
      return state.lastCheckedAt ? 'degraded' : 'unknown'
    },
    levelLabel(): string {
      switch (this.level) {
        case 'ok':
          return '服务正常'
        case 'degraded':
          return '部分不可用'
        case 'down':
          return '连接异常'
        default:
          return '状态未知'
      }
    },
  },
  actions: {
    async refresh(): Promise<void> {
      this.checking = true
      try {
        // 1) health：HTTP 200 也要检查 status 与 database 字段
        try {
          const body = await api.health()
          this.health = body
          this.healthFieldsOk = healthFieldsOk(body)
          this.networkDown = false
        } catch (err) {
          if (err instanceof ApiError && err.kind === 'network') {
            this.networkDown = true
            this.health = null
            this.healthFieldsOk = null
            this.ready = null
            this.checks = null
            this.readyHttpStatus = null
            this.lastCheckedAt = new Date().toISOString()
            return
          }
          this.health = null
          this.healthFieldsOk = false
        }
        // 2) ready：503 也要解析响应体中的 checks
        try {
          const { httpStatus, body } = await api.ready()
          this.readyHttpStatus = httpStatus
          if (body) {
            this.ready = Boolean(body.ready) && httpStatus === 200
            this.checks = body.checks ?? null
          } else {
            this.ready = httpStatus === 200
            this.checks = null
          }
        } catch (err) {
          if (err instanceof ApiError && err.kind === 'network') {
            this.networkDown = true
          }
          this.ready = null
          this.checks = null
          this.readyHttpStatus = err instanceof ApiError ? err.status : null
        }
        this.lastCheckedAt = new Date().toISOString()
      } finally {
        this.checking = false
      }
    },
    /** 任意请求层捕获到网络级失败时调用，点亮顶部连接异常提示条 */
    markNetworkIssue(): void {
      this.networkDown = true
    },
    clearNetworkIssue(): void {
      this.networkDown = false
    },
  },
})
