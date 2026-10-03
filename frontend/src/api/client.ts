import {
  apiFetch,
  apiFetchRaw,
  ApiError,
  parseDetail,
  API_ROOT,
} from './http'
import { isMockEnabled } from './mockFlag'
import { toFiniteNumber } from '../utils/number'
import type {
  ContextItem,
  CreateRunRequest,
  CreateRunResponse,
  EvidenceItem,
  GeneRow,
  GenesResponse,
  HealthResponse,
  MetabolicTasksResponse,
  PerturbationList,
  ProjectionPoint,
  ProjectionResponse,
  ReactionRow,
  ReactionsResponse,
  ReadyResponse,
  RunRecord,
  RunMode,
  RunProvenance,
  RunValidation,
  RunSummary,
} from '../types/run'

/**
 * 端点封装与返回值适配（字符串数值统一在此转换）。
 *
 * Mock 分发：仅当显式开关（VITE_ENABLE_MOCK=true 或界面本机开关）开启时，
 * 才动态引入 src/fixtures/mockApi 返回样例数据；开关关闭时完全不引用 fixtures。
 * 真实请求失败不会自动切换到 mock（无任何 fallback 逻辑）。
 */

const loadMock = () => import('../fixtures/mockApi')

export const api = {
  async health(signal?: AbortSignal): Promise<HealthResponse> {
    if (isMockEnabled()) return (await loadMock()).health()
    return apiFetch<HealthResponse>('/health', { signal, timeoutMs: 10000 })
  },

  /** /ready：200 与 503 都需要解析响应体 */
  async ready(signal?: AbortSignal): Promise<{ httpStatus: number; body: ReadyResponse | null }> {
    if (isMockEnabled()) return (await loadMock()).ready()
    const raw = await apiFetchRaw('/ready', { signal, timeoutMs: 10000 })
    if (raw.status === 200 || raw.status === 503) {
      return { httpStatus: raw.status, body: (raw.data as ReadyResponse | null) ?? null }
    }
    const parsed = parseDetail(
      raw.data && typeof raw.data === 'object' && 'detail' in (raw.data as Record<string, unknown>)
        ? (raw.data as Record<string, unknown>).detail
        : raw.data,
      `HTTP ${raw.status}`,
    )
    throw new ApiError({
      kind: 'http',
      status: raw.status,
      code: parsed.code,
      message: parsed.message,
      endpoint: '/ready',
    })
  },

  async contexts(signal?: AbortSignal): Promise<ContextItem[]> {
    if (isMockEnabled()) return (await loadMock()).contexts()
    return apiFetch<ContextItem[]>('/catalog/contexts', { signal })
  },

  async perturbations(cellLine: string, mode: RunMode = 'online', signal?: AbortSignal): Promise<PerturbationList> {
    if (isMockEnabled()) return (await loadMock()).perturbations(cellLine, mode)
    return apiFetch<PerturbationList>('/catalog/perturbations', {
      query: { cell_line: cellLine, mode },
      signal,
    })
  },

  /** 创建任务：HTTP 202 仅表示已接收；超时 30s 后提示「提交结果待确认」，不自动重发 */
  async createRun(payload: CreateRunRequest): Promise<CreateRunResponse> {
    if (isMockEnabled()) return (await loadMock()).createRun(payload)
    return apiFetch<CreateRunResponse>('/runs', {
      method: 'POST',
      body: payload,
      timeoutMs: 30000,
    })
  },

  async getRun(runId: string, signal?: AbortSignal): Promise<RunRecord> {
    if (isMockEnabled()) return (await loadMock()).getRun(runId)
    return apiFetch<RunRecord>(`/runs/${encodeURIComponent(runId)}`, { signal })
  },

  async getSummary(runId: string, signal?: AbortSignal): Promise<RunSummary> {
    if (isMockEnabled()) return (await loadMock()).getSummary(runId)
    return apiFetch<RunSummary>(`/runs/${encodeURIComponent(runId)}/summary`, { signal })
  },

  async getProvenance(runId: string, signal?: AbortSignal): Promise<RunProvenance> {
    if (isMockEnabled()) throw new ApiError({kind:'http', status:404, code:'ARTIFACT_NOT_FOUND',
      message:'Mock 合成样例不提供真实运行哈希', endpoint:`/runs/${runId}/provenance`})
    return apiFetch<RunProvenance>(`/runs/${encodeURIComponent(runId)}/provenance`, {signal})
  },

  async getValidation(runId: string, signal?: AbortSignal): Promise<RunValidation> {
    if (isMockEnabled()) throw new ApiError({kind:'http', status:404, code:'ARTIFACT_NOT_FOUND',
      message:'Mock 合成样例不提供科学验证指标', endpoint:`/runs/${runId}/validation`})
    return apiFetch<RunValidation>(`/runs/${encodeURIComponent(runId)}/validation`, {signal})
  },

  async getProjection(runId: string, signal?: AbortSignal): Promise<ProjectionResponse> {
    if (isMockEnabled()) return (await loadMock()).getProjection(runId)
    const raw = await apiFetch<{
      method?: string
      seed?: number
      points?: Array<Record<string, unknown>>
    }>(`/runs/${encodeURIComponent(runId)}/projection`, { signal })
    const points: ProjectionPoint[] = (raw.points ?? [])
      .map((p) => ({
        x: toFiniteNumber(p.x),
        y: toFiniteNumber(p.y),
        source: p.source,
        cell_index: toFiniteNumber(p.cell_index),
      }))
      .filter(
        (p): p is ProjectionPoint =>
          p.x !== null &&
          p.y !== null &&
          p.cell_index !== null &&
          (p.source === 'control' || p.source === 'predicted' || p.source === 'observed'),
      )
    return { method: raw.method ?? 'seeded-random-projection', seed: raw.seed ?? 0, points }
  },

  /** genes：CSV 转 JSON，数字是字符串，统一转换为 number | null */
  async getGenes(runId: string, limit = 2000, signal?: AbortSignal): Promise<GenesResponse> {
    if (isMockEnabled()) return (await loadMock()).getGenes(runId, limit)
    const raw = await apiFetch<{ items?: Array<Record<string, unknown>>; limit: number; truncated: boolean }>(
      `/runs/${encodeURIComponent(runId)}/genes`,
      { query: { limit }, signal },
    )
    const items: GeneRow[] = (raw.items ?? []).map((row) => ({
      gene: String(row.gene ?? ''),
      control: toFiniteNumber(row.control),
      predicted: toFiniteNumber(row.predicted),
      predicted_delta: toFiniteNumber(row.predicted_delta),
      observed: toFiniteNumber(row.observed),
      observed_delta: toFiniteNumber(row.observed_delta),
    }))
    return { items, limit: raw.limit, truncated: Boolean(raw.truncated) }
  },

  async getMetabolicTasks(
    runId: string,
    limit = 1000,
    signal?: AbortSignal,
  ): Promise<MetabolicTasksResponse> {
    if (isMockEnabled()) return (await loadMock()).getMetabolicTasks(runId, limit)
    const raw = await apiFetch<{ items?: Array<Record<string, unknown>>; limit: number; truncated: boolean; scope?: 'top' | 'all'; total?: number; excluded_count?: number }>(
      `/runs/${encodeURIComponent(runId)}/metabolic-tasks`,
      { query: { limit, scope: 'all' }, signal },
    )
    const items: EvidenceItem[] = (raw.items ?? []).map((row) => normalizeEvidence(row))
    return { items, limit: raw.limit, truncated: Boolean(raw.truncated), scope: raw.scope, total: raw.total, excluded_count: raw.excluded_count }
  },

  /** reactions：旧运行可能是宽表结构（后端返回 500 INVALID_ARTIFACT）或 404，由调用方降级展示 */
  async getReactions(runId: string, limit = 1000, signal?: AbortSignal): Promise<ReactionsResponse> {
    if (isMockEnabled()) return (await loadMock()).getReactions(runId, limit)
    const raw = await apiFetch<{
      items?: Array<Record<string, unknown>>
      limit: number
      truncated: boolean
    }>(`/runs/${encodeURIComponent(runId)}/reactions`, { query: { limit }, signal })
    const items: ReactionRow[] = (raw.items ?? []).map((row) => ({
      reaction: String(row.reaction ?? ''),
      control: toFiniteNumber(row.control),
      predicted: toFiniteNumber(row.predicted),
      predicted_delta: toFiniteNumber(row.predicted_delta),
    }))
    return { items, limit: raw.limit, truncated: Boolean(raw.truncated) }
  },

  /** 报告下载：成功返回 Blob；404 表示未提供报告 */
  async downloadReport(runId: string): Promise<{ blob: Blob; filename: string }> {
    if (isMockEnabled()) return (await loadMock()).downloadReport(runId)
    const raw = await apiFetchRaw(`/runs/${encodeURIComponent(runId)}/report`, { timeoutMs: 60000 })
    if (!raw.ok) {
      const detail =
        raw.data && typeof raw.data === 'object' && 'detail' in (raw.data as Record<string, unknown>)
          ? (raw.data as Record<string, unknown>).detail
          : raw.data
      const parsed = parseDetail(detail, `HTTP ${raw.status}`)
      throw new ApiError({
        kind: 'http',
        status: raw.status,
        code: parsed.code,
        message:
          raw.status === 404 && (parsed.code === 'ARTIFACT_NOT_FOUND' || parsed.code === null)
            ? '该运行未提供报告'
            : parsed.message,
        endpoint: `/runs/${runId}/report`,
        detail,
      })
    }
    const body = typeof raw.data === 'string' ? raw.data : JSON.stringify(raw.data, null, 2)
    return {
      blob: new Blob([body], { type: 'text/html;charset=utf-8' }),
      filename: `celllens-${runId}.html`,
    }
  },
}

function normalizeEvidence(row: Record<string, unknown>): EvidenceItem {
  const level = row.evidence_level
  return {
    id: String(row.id ?? ''),
    label: String(row.label ?? row.id ?? ''),
    predicted_delta: toFiniteNumber(row.predicted_delta) ?? 0,
    observed_delta: toFiniteNumber(row.observed_delta),
    coverage: toFiniteNumber(row.coverage) ?? 0,
    evidence_level:
      level === 'supported' || level === 'exploratory' || level === 'insufficient'
        ? level
        : 'insufficient',
    determinant_genes: Array.isArray(row.determinant_genes)
      ? row.determinant_genes.map((g) => String(g))
      : [],
  }
}

export { API_ROOT }
