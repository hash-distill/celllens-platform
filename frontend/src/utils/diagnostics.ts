import { API_ROOT } from '../api/http'
import type { ApiError } from '../api/http'

export interface DiagnosticsInput {
  endpoint?: string
  httpStatus?: number | null
  runId?: string
  params?: unknown
  errorCode?: string | null
  message?: string | null
  extraLines?: string[]
}

/**
 * 组装「复制诊断信息」文本。
 * 只包含 API 基址、HTTP 状态、接口、run_id、参数、错误码与页面版本；
 * 不包含数据库凭据或服务端本地私密路径。
 */
export function buildDiagnostics(input: DiagnosticsInput): string {
  const lines: string[] = [
    'CellLens 细胞知镜 · 运行诊断信息',
    `页面版本: ${__APP_VERSION__}`,
    `API 基址: ${API_ROOT}`,
    `采集时间: ${new Date().toISOString()}`,
  ]
  if (input.endpoint) lines.push(`接口: ${input.endpoint}`)
  if (input.httpStatus !== undefined && input.httpStatus !== null) lines.push(`HTTP 状态: ${input.httpStatus}`)
  if (input.runId) lines.push(`run_id: ${input.runId}`)
  if (input.params !== undefined) lines.push(`请求参数: ${JSON.stringify(input.params)}`)
  if (input.errorCode) lines.push(`错误码: ${input.errorCode}`)
  if (input.message) lines.push(`错误信息: ${input.message}`)
  if (input.extraLines) lines.push(...input.extraLines)
  return lines.join('\n')
}

export function diagnosticsFromError(error: ApiError, runId?: string, params?: unknown): string {
  return buildDiagnostics({
    endpoint: error.endpoint,
    httpStatus: error.status,
    runId,
    params,
    errorCode: error.code ?? undefined,
    message: error.message,
  })
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // 剪贴板 API 不可用时的回退
    try {
      const area = document.createElement('textarea')
      area.value = text
      area.style.position = 'fixed'
      area.style.opacity = '0'
      document.body.appendChild(area)
      area.select()
      document.execCommand('copy')
      document.body.removeChild(area)
      return true
    } catch {
      return false
    }
  }
}
