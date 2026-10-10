import { isMockEnabled } from '../api/mockFlag'
import type { ResultKind, RunMode } from '../types/run'

export function isSyntheticResult(mode?: RunMode, runId = '', kind?: ResultKind | null): boolean {
  return isMockEnabled() || runId.startsWith('mock_') || (mode === 'precomputed' && kind !== 'frozen_model_result')
}

export function runSourceLabel(mode?: RunMode, runId = '', kind?: ResultKind | null): string {
  if (isMockEnabled() || runId.startsWith('mock_run_')) return '合成数据（开发记录）'
  if (mode === 'precomputed') return kind === 'frozen_model_result' ? '真实结果回放（本次未重新计算）' : '合成数据（历史记录）'
  if (mode === 'online') return '在线预测（真实计算）'
  if (mode === 'validation') return '实测对照（匹配观测分析）'
  return '来源未提供'
}
