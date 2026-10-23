export type ModelProvider = 'openai' | 'gemini' | 'anthropic' | 'deepseek' | 'siliconflow' | 'custom'
export type ReasoningEffort = 'auto' | 'none' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh' | 'max'
export interface ModelPreferences {
  provider: ModelProvider
  base_url: string
  model: string
  max_tokens: number | null
  token_parameter: 'max_completion_tokens' | 'max_tokens'
  reasoning_effort: ReasoningEffort
  thinking_mode: 'auto' | 'enabled' | 'adaptive' | 'disabled'
  thinking_budget: number
  context_window: number | null
}
export interface DiscoveredModel {id: string; name: string; context_window?: number; max_output_tokens?: number}
export interface ProviderPreset {
  id: ModelProvider
  label: string
  base_url: string
  protocol: 'chat/completions' | 'messages'
  token_parameter: 'max_completion_tokens' | 'max_tokens'
  reasoning_efforts: ReasoningEffort[]
}
