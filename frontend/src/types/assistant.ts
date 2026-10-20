export type ModelProvider = 'openai' | 'gemini' | 'anthropic' | 'deepseek' | 'siliconflow' | 'custom'
export interface ProviderPreset {
  id: ModelProvider
  label: string
  base_url: string
  protocol: 'chat/completions' | 'messages'
  token_parameter: 'max_completion_tokens' | 'max_tokens'
}
