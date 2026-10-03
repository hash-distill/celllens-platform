/** CSV 导出：仅导出前端已加载、已公开的数据，文件名注明 run_id、是否截断与来源 */

function escapeCell(value: string): string {
  if (/[",\n\r]/.test(value)) return `"${value.replace(/"/g, '""')}"`
  return value
}

export function buildCsv(headers: string[], rows: string[][]): string {
  const lines = [headers.map(escapeCell).join(',')]
  for (const row of rows) lines.push(row.map(escapeCell).join(','))
  return lines.join('\r\n')
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function downloadCsv(filename: string, headers: string[], rows: string[][]): void {
  // 带 BOM，保证 Excel 正确识别 UTF-8 中文
  const blob = new Blob([`﻿${buildCsv(headers, rows)}`], { type: 'text/csv;charset=utf-8' })
  downloadBlob(blob, filename)
}
