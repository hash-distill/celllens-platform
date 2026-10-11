import { apiFetch } from './http'
import type { ModelPreferences } from '../stores/preferences'
export interface AssistantContext {source_kind: 'run' | 'analysis'; source_id: string; scope: string; context_sha256: string; artifact_sha256: Record<string,string>; system_prompt: string; data: Record<string,unknown>}
export interface AssistantResult {text: string; model: string; base_url: string; finish_reason: string; usage: Record<string,number>; generated_at: string; context_sha256?: string; source_id?: string; purpose?: string}
export type Purpose = 'interpret' | 'coverage' | 'next_steps'
export const purposeLabels: Record<Purpose,string> = {interpret: '解读主要结果', coverage: '解释覆盖与局限', next_steps: '建议后续验证工作'}
type Connection = ModelPreferences & {api_key: string}
export const assistantApi = {
  capabilities: () => apiFetch<{allowed_origins: string[]; timeout_seconds: number}>('/assistant/capabilities'),
  context: (kind: string, id: string, signal?: AbortSignal) => apiFetch<AssistantContext>('/assistant/context', {query: {source_kind: kind, source_id: id}, signal}),
  test: (connection: Connection, signal?: AbortSignal) => apiFetch<AssistantResult>('/assistant/test', {method: 'POST', body: connection, timeoutMs: 100000, signal}),
  interpret: (context: AssistantContext, purpose: Purpose, connection: Connection, signal?: AbortSignal) => apiFetch<AssistantResult>('/assistant/interpret', {method: 'POST', body: {...connection, source_kind: context.source_kind, source_id: context.source_id, context_sha256: context.context_sha256, purpose}, timeoutMs: 100000, signal}),
}
