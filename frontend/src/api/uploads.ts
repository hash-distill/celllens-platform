import { ApiError, apiUrl, parseDetail } from './http'

export interface UploadCapabilities {
  available: boolean
  reason?: string
  max_bytes: number
  max_cells: number
  max_genes: number
  max_matrix_elements: number
}
export interface ObsColumn {
  name: string
  dtype: string
  kind: 'categorical' | 'numeric'
  missing_count: number
  unique_count: number
  values: { label: string; count: number }[]
  truncated: boolean
}
export interface H5adUpload {
  upload_id: string
  filename: string
  bytes: number
  sha256: string
  cells: number
  genes: number
  obs_columns: ObsColumn[]
  suggested_cell_line?: string | null
  expires_at?: string
}

/** Send the File itself, without buffering or converting it to JSON/base64. */
export function uploadH5ad(file: File, options: {
  signal?: AbortSignal
  onProgress?: (percent: number) => void
} = {}): Promise<H5adUpload> {
  const endpoint = '/research/uploads'
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    let settled = false
    const finish = (error?: ApiError, data?: H5adUpload) => {
      if (settled) return
      settled = true
      options.signal?.removeEventListener('abort', abort)
      xhr.onload = xhr.onerror = xhr.ontimeout = xhr.onabort = null
      xhr.upload.onprogress = xhr.upload.onload = null
      if (error) reject(error)
      else resolve(data!)
    }
    const failure = (kind: 'network' | 'timeout' | 'abort', message: string) =>
      new ApiError({ kind, status: null, code: null, message, endpoint })
    const abort = () => {
      finish(failure('abort', '上传已取消，可以重新选择文件。'))
      xhr.abort()
    }
    if (options.signal?.aborted) { abort(); return }
    options.signal?.addEventListener('abort', abort, { once: true })
    xhr.upload.onprogress = event => {
      if (!settled && event.lengthComputable && event.total > 0) options.onProgress?.(Math.min(100, Math.floor(event.loaded / event.total * 100)))
    }
    xhr.upload.onload = () => { if (!settled) options.onProgress?.(100) }
    xhr.onload = () => {
      if (settled) return
      let data: unknown
      try { data = JSON.parse(xhr.responseText) } catch { data = xhr.responseText }
      if (xhr.status >= 200 && xhr.status < 300) {
        if (data && typeof data === 'object' && typeof (data as H5adUpload).upload_id === 'string' && Array.isArray((data as H5adUpload).obs_columns)) {
          finish(undefined, data as H5adUpload)
        } else finish(failure('network', '未收到有效的文件字段信息，请重新上传。'))
      } else {
        const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : data
        finish(new ApiError({ kind: 'http', status: xhr.status, endpoint, detail, ...parseDetail(detail, `上传失败（HTTP ${xhr.status}），请重试。`) }))
      }
    }
    xhr.onerror = () => finish(failure('network', '上传连接中断，请检查网络后重试。'))
    xhr.ontimeout = () => finish(failure('timeout', '上传或字段读取超时，请重试或选择较小的 H5AD 文件。'))
    xhr.onabort = () => finish(failure('abort', '上传已取消，可以重新选择文件。'))
    try {
      xhr.open('POST', apiUrl(endpoint, { filename: file.name }))
      xhr.timeout = 600000
      // XHR's default sends same-origin cookies, matching apiFetch.
      xhr.withCredentials = false
      xhr.setRequestHeader('Content-Type', 'application/octet-stream')
      xhr.send(file)
    } catch {
      finish(failure('network', '无法开始上传，请检查连接后重试。'))
    }
  })
}
