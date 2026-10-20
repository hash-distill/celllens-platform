/**
 * HTTP 请求层：统一错误解析（detail 可能是对象 / 数组 / 字符串）、
 * 超时与取消、网络错误识别。组件不直接拼接请求地址。
 */

export interface FieldError {
  loc: string
  msg: string
}

export interface ParsedDetail {
  code: string | null
  message: string
  fieldErrors: FieldError[]
  extras: Record<string, unknown>
}

/** 解析 FastAPI 错误 detail：对象 {code,message,...}、数组（422 校验）或字符串 */
export function parseDetail(detail: unknown, fallback: string): ParsedDetail {
  const out: ParsedDetail = { code: null, message: fallback, fieldErrors: [], extras: {} }
  if (typeof detail === 'string') {
    out.message = detail
    return out
  }
  if (Array.isArray(detail)) {
    for (const item of detail) {
      if (item && typeof item === 'object') {
        const rec = item as Record<string, unknown>
        const loc = Array.isArray(rec.loc)
          ? rec.loc.map((part) => String(part)).join('.')
          : String(rec.loc ?? '')
        out.fieldErrors.push({ loc, msg: String(rec.msg ?? rec.message ?? '') })
      }
    }
    if (out.fieldErrors.length > 0) {
      out.message = out.fieldErrors.map((f) => `${f.loc}：${f.msg}`).join('；')
    }
    return out
  }
  if (detail && typeof detail === 'object') {
    const rec = detail as Record<string, unknown>
    out.code = typeof rec.code === 'string' ? rec.code : null
    if (typeof rec.message === 'string') out.message = rec.message
    for (const [key, value] of Object.entries(rec)) {
      if (key !== 'code' && key !== 'message') out.extras[key] = value
    }
    return out
  }
  return out
}

export type ApiErrorKind = 'http' | 'network' | 'timeout' | 'abort'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null
  readonly code: string | null
  readonly fieldErrors: FieldError[]
  readonly extras: Record<string, unknown>
  readonly endpoint: string
  readonly detail: unknown

  constructor(init: {
    kind: ApiErrorKind
    status: number | null
    code: string | null
    message: string
    endpoint: string
    fieldErrors?: FieldError[]
    extras?: Record<string, unknown>
    detail?: unknown
  }) {
    super(init.message)
    this.name = 'ApiError'
    this.kind = init.kind
    this.status = init.status
    this.code = init.code
    this.message = init.message
    this.endpoint = init.endpoint
    this.fieldErrors = init.fieldErrors ?? []
    this.extras = init.extras ?? {}
    this.detail = init.detail
  }
}

const rawBase = ((import.meta.env.VITE_API_BASE as string | undefined) ?? '').trim() || '/api'
/** 可配置 API 基址（默认 /api，开发时经 Vite 代理转发到后端） */
export const API_BASE = rawBase.replace(/\/+$/, '')
/** 含版本前缀的完整根地址，例如 /api/v1 */
export const API_ROOT = `${API_BASE}/v1`

export function apiUrl(path: string, query?: Record<string, string | number | boolean | undefined>): string {
  const url = new URL(`${API_ROOT}${path}`, window.location.origin)
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, String(value))
    }
  }
  return url.toString()
}

export interface RawResponse {
  status: number
  ok: boolean
  data: unknown
}

export interface RequestOptions {
  responseType?: 'json' | 'blob'
  method?: 'GET' | 'POST'
  body?: unknown
  headers?: Record<string, string>
  query?: Record<string, string | number | boolean | undefined>
  signal?: AbortSignal
  timeoutMs?: number
}

/**
 * 底层请求：返回原始状态与响应体（不抛出 HTTP 错误），
 * 供 /ready 503 等需要解析错误响应体的场景使用。
 */
export async function apiFetchRaw(path: string, opts: RequestOptions = {}): Promise<RawResponse> {
  const endpoint = path
  const controller = new AbortController()
  let timedOut = false
  const external = opts.signal ?? null
  const onExternalAbort = () => controller.abort()
  if (external) {
    if (external.aborted) {
      throw new ApiError({ kind: 'abort', status: null, code: null, message: '请求已取消', endpoint })
    }
    external.addEventListener('abort', onExternalAbort)
  }
  let timer: number | undefined
  const timeoutMs = opts.timeoutMs ?? 30000
  if (timeoutMs > 0) {
    timer = window.setTimeout(() => {
      timedOut = true
      controller.abort()
    }, timeoutMs)
  }

  try {
    const res = await fetch(apiUrl(path, opts.query), {
      method: opts.method ?? 'GET',
      headers: {
        ...(opts.body !== undefined && !(opts.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
        ...opts.headers,
      },
      body: opts.body instanceof FormData ? opts.body : opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      credentials: 'same-origin',
      signal: controller.signal,
    })
    let data: unknown = null
    if (opts.responseType === 'blob' && res.ok) {
      data = await res.blob()
    } else {
      const text = await res.text()
      if (text.length > 0) {
        try {
          data = JSON.parse(text)
        } catch {
          data = text
        }
      }
    }
    return { status: res.status, ok: res.ok, data }
  } catch {
    if (timedOut) {
      throw new ApiError({
        kind: 'timeout',
        status: null,
        code: 'TIMEOUT',
        message: opts.method === 'POST'
          ? '请求超时：服务端可能已接收，提交结果待确认'
          : '读取超时，请重试；已有结果与任务状态保持不变',
        endpoint,
      })
    }
    if (controller.signal.aborted) {
      throw new ApiError({ kind: 'abort', status: null, code: null, message: '请求已取消', endpoint })
    }
    throw new ApiError({
      kind: 'network',
      status: null,
      code: null,
      message: '无法连接后端服务（网络错误或跨域被拦截）',
      endpoint,
    })
  } finally {
    if (external) external.removeEventListener('abort', onExternalAbort)
    if (timer !== undefined) window.clearTimeout(timer)
  }
}

/** 常规请求：非 2xx 抛出 ApiError（已解析三种 detail 结构） */
export async function apiFetch<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const raw = await apiFetchRaw(path, opts)
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
      message: parsed.message,
      fieldErrors: parsed.fieldErrors,
      extras: parsed.extras,
      endpoint: path,
      detail,
    })
  }
  return raw.data as T
}
