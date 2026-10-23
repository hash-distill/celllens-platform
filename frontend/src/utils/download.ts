import { apiUrl, parseDetail } from '../api/http'

export type DownloadFormat = 'csv'|'zip'|'svg'|'png'|'pdf'|'json'
export interface DownloadFile {blob: Blob; filename: string}
interface DownloadOptions {
  format: DownloadFormat
  filename: string
  query?: Record<string, string | number | boolean | undefined>
  signal?: AbortSignal
  timeoutMs?: number
}
const mimeTypes: Record<DownloadFormat, string[]> = {
  csv:['text/csv','application/csv'], zip:['application/zip','application/x-zip-compressed'],
  svg:['image/svg+xml'], png:['image/png'], pdf:['application/pdf'], json:['application/json'],
}

// SHA-256 compression constants, for browsers on plain HTTP without SubtleCrypto.
const sha256Constants = new Uint32Array([
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
])
function rotateRight(word: number, bits: number): number { return (word >>> bits) | (word << (32-bits)) }
function sha256Portable(bytes: Uint8Array): string {
  const padded = new Uint8Array(Math.ceil((bytes.length+9)/64)*64)
  padded.set(bytes); padded[bytes.length] = 0x80
  const view = new DataView(padded.buffer)
  view.setUint32(padded.length-8, Math.floor(bytes.length/0x20000000))
  view.setUint32(padded.length-4, (bytes.length*8) >>> 0)
  const state = new Uint32Array([0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19])
  const words = new Uint32Array(64)
  for (let offset=0; offset<padded.length; offset+=64) {
    for (let index=0; index<16; index++) words[index] = view.getUint32(offset+index*4)
    for (let index=16; index<64; index++) {
      const left = words[index-15]!, right = words[index-2]!
      const sigma0 = rotateRight(left,7) ^ rotateRight(left,18) ^ (left >>> 3)
      const sigma1 = rotateRight(right,17) ^ rotateRight(right,19) ^ (right >>> 10)
      words[index] = (words[index-16]! + sigma0 + words[index-7]! + sigma1) >>> 0
    }
    let [a,b,c,d,e,f,g,h] = Array.from(state) as [number,number,number,number,number,number,number,number]
    for (let index=0; index<64; index++) {
      const sum1 = rotateRight(e,6) ^ rotateRight(e,11) ^ rotateRight(e,25)
      const sum0 = rotateRight(a,2) ^ rotateRight(a,13) ^ rotateRight(a,22)
      const temp1 = (h + sum1 + ((e & f) ^ (~e & g)) + sha256Constants[index]! + words[index]!) >>> 0
      const temp2 = (sum0 + ((a & b) ^ (a & c) ^ (b & c))) >>> 0
      h=g; g=f; f=e; e=(d+temp1) >>> 0; d=c; c=b; b=a; a=(temp1+temp2) >>> 0
    }
    const result = [a,b,c,d,e,f,g,h]
    for (let index=0; index<8; index++) state[index] = (state[index]!+result[index]!) >>> 0
  }
  return Array.from(state, word => word.toString(16).padStart(8,'0')).join('')
}

export async function featureFilenameToken(feature: string): Promise<string> {
  const slug = feature.replace(/[^A-Za-z0-9_-]+/g, '_').replace(/^[_-]+|[_-]+$/g, '').slice(0,48) || 'feature'
  const bytes = new TextEncoder().encode(feature), subtle = globalThis.crypto?.subtle
  const hash = subtle
    ? Array.from(new Uint8Array(await subtle.digest('SHA-256',bytes)), value => value.toString(16).padStart(2,'0')).join('')
    : sha256Portable(bytes)
  return `${slug}-${hash.slice(0,8)}`
}

function responseFilename(disposition: string | null, fallback: string): string {
  if (!disposition) return fallback
  const encoded = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(disposition)
  const plain = /filename\s*=\s*(?:"([^"]+)"|([^;]+))/i.exec(disposition)
  let name = plain?.[1] ?? plain?.[2]?.trim() ?? fallback
  if (encoded) {
    try { name = decodeURIComponent(encoded[1]!.trim().replace(/^"|"$/g,'')) } catch { throw new Error('下载文件名编码无效') }
  }
  if (/[\\/\x00-\x1f]/.test(name) || !name.trim()) throw new Error('下载文件名无效')
  return name
}

async function validateContent(blob: Blob, format: DownloadFormat) {
  const bytes = new Uint8Array(await blob.slice(0,512).arrayBuffer())
  const prefix = new TextDecoder().decode(bytes).replace(/^\uFEFF/,'').trimStart()
  const valid = format === 'pdf' ? prefix.startsWith('%PDF-')
    : format === 'png' ? [137,80,78,71,13,10,26,10].every((byte,index) => bytes[index] === byte)
    : format === 'zip' ? bytes[0] === 80 && bytes[1] === 75 && ((bytes[2] === 3 && bytes[3] === 4) || (bytes[2] === 5 && bytes[3] === 6))
    : format === 'svg' ? /<svg[\s>]/i.test(prefix)
    : format === 'json' ? /^[{\[]/.test(prefix)
    : !!bytes.length && !/^(?:<!doctype|<html|\{"detail"\s*:)/i.test(prefix)
  if (!valid) throw new Error('下载内容与所选文件类型不符，请重试')
}

/** Validate responses before exposing a browser download; cancellation covers body reads too. */
export async function fetchDownload(path: string, options: DownloadOptions): Promise<DownloadFile> {
  const controller = new AbortController(), external = options.signal
  let timedOut = false
  if (external?.aborted) throw new Error('下载已取消')
  const onAbort = () => controller.abort()
  external?.addEventListener('abort', onAbort, {once:true})
  const timer = window.setTimeout(() => {timedOut = true; controller.abort()}, options.timeoutMs ?? 120000)
  try {
    const response = await fetch(apiUrl(path, options.query), {credentials:'same-origin',signal:controller.signal})
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new Error(parseDetail(body?.detail, `下载失败：HTTP ${response.status}`).message)
    }
    const mime = (response.headers.get('content-type') ?? '').split(';')[0]!.trim().toLowerCase()
    if (!mimeTypes[options.format].includes(mime)) throw new Error('下载文件类型与所选格式不符，请重试')
    const filename = responseFilename(response.headers.get('content-disposition'), options.filename)
    if (!filename.toLowerCase().endsWith(`.${options.format}`)) throw new Error('下载文件后缀与所选格式不符，请重试')
    const blob = await response.blob()
    await validateContent(blob, options.format)
    if (controller.signal.aborted) throw new Error('下载已取消')
    return {blob,filename}
  } catch(error) {
    if (timedOut) throw new Error('下载超时，请重试')
    if (controller.signal.aborted) throw new Error('下载已取消')
    throw error
  } finally {
    window.clearTimeout(timer)
    external?.removeEventListener('abort', onAbort)
  }
}
