/** CSV 清单导出；数字保持数值，文本强制避免电子表格公式解释。 */
type CsvCell = string | number | null | undefined

function escapeCell(value: CsvCell): string {
  let text = value == null ? '' : String(value)
  if (typeof value === 'string' && /^[\s\uFEFF]*[=+\-@]/.test(text)) text = "'" + text
  if (/[",\n\r]/.test(text)) return `"${text.replace(/"/g, '""')}"`
  return text
}

export function buildCsv(headers: string[], rows: CsvCell[][]): string {
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

export function downloadCsv(filename: string, headers: string[], rows: CsvCell[][]): void {
  // 带 BOM，保证 Excel 正确识别 UTF-8 中文
  const blob = new Blob([`﻿${buildCsv(headers, rows)}`], { type: 'text/csv;charset=utf-8' })
  downloadBlob(blob, filename)
}
