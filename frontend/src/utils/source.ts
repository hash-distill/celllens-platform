import { isMockEnabled } from '../api/mockFlag'
import type { RunMode } from '../types/run'

export function runSourceLabel(mode?: RunMode, runId = ''): string {
  if (isMockEnabled() || runId.startsWith('mock_run_')) return 'Mock 合成样例'
  if (mode === 'precomputed') return '合成演示（precomputed）'
  if (mode === 'online') return '在线预测（真实计算）'
  if (mode === 'validation') return '匹配观测计算（协议待确认）'
  return '来源未提供'
}
