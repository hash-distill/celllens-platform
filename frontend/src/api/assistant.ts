import { apiFetch } from './http'
import type { ModelPreferences } from '../stores/preferences'
import type { DiscoveredModel, ModelProvider, ProviderPreset } from '../types/assistant'
export interface AssistantSelection {view: 'overview'|'chart'|'genes'|'metabolism'|'comparison'; embedding?: 'pca'|'umap'; space?: 'expression'|'metabolic'; feature_kind?: 'gene'|'task'; feature_id?: string}
export type AssistantSourceKind = 'run' | 'measured'
export interface AssistantContext {source_kind: AssistantSourceKind; source_id: string; selection: AssistantSelection; scope: string; context_sha256: string; artifact_sha256: Record<string,string>; system_prompt: string; data: Record<string,unknown>; request_budget?:{system_bytes:number; user_bytes:Partial<Record<Purpose,number>>; estimator:string}}
export interface AssistantResult {text: string; model: string; provider?: ModelProvider; base_url: string; finish_reason: string; usage: Record<string,number>; generated_at: string; context_sha256?: string; source_kind?: AssistantSourceKind; source_id?: string; purpose?: string; question?: string; selection?: AssistantSelection}
export type Purpose = 'interpret' | 'coverage' | 'next_steps' | 'figure' | 'genes' | 'metabolism' | 'comparison'
export const purposeLabels: Record<Purpose,string> = {figure: '解读当前科研图', interpret: '解读主要结果', genes: '分析基因表达变化', metabolism: '分析代谢任务变化', comparison: '比较预测与实测', coverage: '解读数据覆盖', next_steps: '建议后续研究方向'}
type Connection = ModelPreferences & {api_key: string}
async function ensureDefaultLengths(connection: Connection, signal?: AbortSignal) {
  if (connection.max_tokens !== null && connection.context_window !== null) return
  const capabilities = await apiFetch<{model_default_lengths?: boolean}>('/assistant/capabilities', {signal})
  if (!capabilities.model_default_lengths) throw new Error('后台尚未支持模型默认长度，请重启 CellLens 分析服务后再生成解读。')
}
export const assistantApi = {
  capabilities: () => apiFetch<{providers: ProviderPreset[]; allowed_origins: string[]; timeout_seconds: number; model_default_lengths?: boolean}>('/assistant/capabilities'),
  models: (connection: Pick<Connection,'provider'|'base_url'|'api_key'>, signal?: AbortSignal) => apiFetch<{models:DiscoveredModel[]; truncated:boolean}>('/assistant/models', {method:'POST',body:connection,timeoutMs:100000,signal}),
  context: async (kind: AssistantSourceKind, id: string, signal?: AbortSignal, selection: AssistantSelection = {view:'overview'}) => {
    const context = await apiFetch<AssistantContext>('/assistant/context', {query:{source_kind:kind,source_id:id,...selection},timeoutMs:100000,signal})
    if (!context.selection || (selection.view === 'comparison' && (context.selection.view !== 'comparison' || !context.artifact_sha256?.['comparison_manifest.json']))) throw new Error('当前后台仍是旧版本，请重启 CellLens 分析服务后再生成解读。')
    return context
  },
  test: async (connection: Connection, signal?: AbortSignal) => {
    await ensureDefaultLengths(connection, signal)
    return apiFetch<AssistantResult>('/assistant/test', {method: 'POST', body: connection, timeoutMs: 100000, signal})
  },
  interpret: async (context: AssistantContext, purpose: Purpose, connection: Connection, signal?: AbortSignal, question = '') => {
    await ensureDefaultLengths(connection, signal)
    return apiFetch<AssistantResult>('/assistant/interpret', {method: 'POST', body: {...connection, source_kind: context.source_kind, source_id: context.source_id, context_sha256: context.context_sha256, ...context.selection, purpose, question}, timeoutMs: 100000, signal})
  },
}
