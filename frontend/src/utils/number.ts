/** 数值解析与校验：CSV 转 JSON 的接口数字是字符串，统一在此转换。 */

/**
 * 把任意输入转换为有限数值。
 * 空串、null、undefined、非数值、非有限数值一律返回 null（页面显示「未提供」，不得转 0）。
 */
export function toFiniteNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (trimmed === '') return null
    const parsed = Number(trimmed)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

/** 判断输入是否为合法整数且在范围内 */
export function isIntegerInRange(value: string | number, min: number, max: number): boolean {
  if (typeof value === 'string' && !/^-?\d+$/.test(value.trim())) return false
  const parsed = typeof value === 'number' ? value : Number(value.trim())
  return Number.isSafeInteger(parsed) && parsed >= min && parsed <= max
}
