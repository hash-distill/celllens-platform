import type { ModelPreferences, ModelProvider, ReasoningEffort } from '../types/assistant'

export const DEFAULT_MODEL: ModelPreferences = {
  provider:'openai', base_url:'https://api.openai.com/v1', model:'', max_tokens:null,
  token_parameter:'max_completion_tokens', reasoning_effort:'auto', thinking_mode:'auto',
  thinking_budget:1024, context_window:null,
}
export const PROVIDER_URLS: Record<ModelProvider,string> = {
  openai:'https://api.openai.com/v1', gemini:'https://generativelanguage.googleapis.com/v1beta/openai',
  anthropic:'https://api.anthropic.com/v1', deepseek:'https://api.deepseek.com',
  siliconflow:'https://api.siliconflow.cn/v1', custom:'',
}
export const EFFORT_OPTIONS: Record<ModelProvider,ReasoningEffort[]> = {
  openai:['auto','none','minimal','low','medium','high','xhigh','max'],
  custom:['auto','none','minimal','low','medium','high','xhigh','max'],
  gemini:['auto','none','minimal','low','medium','high'], deepseek:['auto','none','low','high','max'],
  anthropic:['auto','low','medium','high','xhigh','max'], siliconflow:['auto'],
}
export interface ImportedConnection extends ModelPreferences {name:string; api_key:string}
const fields = Object.keys(DEFAULT_MODEL) as (keyof ModelPreferences)[]
const bad = (message: string): never => {throw new Error(message)}
const object = (value: unknown): value is Record<string,unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value)
function text(value: unknown, fallback: string, limit: number, label: string): string {
  if (value === undefined) return fallback
  if (typeof value !== 'string' || value.length > limit || /[\x00-\x1f\x7f]/.test(value)) return bad(`${label}格式不正确`)
  return value.trim()
}
function integer(value: unknown, fallback: number, min: number, max: number, label: string): number {
  if (value === undefined) return fallback
  const parsed = typeof value === 'string' && /^\d+$/.test(value) ? Number(value) : value
  if (typeof parsed !== 'number' || !Number.isInteger(parsed) || parsed < min || parsed > max) return bad(`${label}须为 ${min}–${max} 的整数`)
  return parsed
}
export function normalizeBaseUrl(value: string): string {
  let parsed: URL
  try {parsed = new URL(value)} catch {return bad('请填写有效的 HTTP(S) 服务地址')}
  if (!['https:','http:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.search || parsed.hash || /%|\/\.\.?($|\/)/.test(value)) return bad('服务地址不能包含认证信息、查询参数或特殊路径')
  return value.trim().replace(/\/+$/,'').replace(/\/(chat\/completions|messages|models)$/,'')
}
function inferProvider(url: string): ModelProvider {
  try {
    const host = new URL(url).hostname
    return (Object.keys(PROVIDER_URLS) as ModelProvider[]).find(key => PROVIDER_URLS[key] && new URL(PROVIDER_URLS[key]).hostname === host) ?? 'custom'
  } catch {return 'custom'}
}
export function cleanPreferences(value: Partial<ModelPreferences>): ModelPreferences {
  const provider = value.provider ?? (value.base_url ? inferProvider(value.base_url) : 'openai')
  if (!Object.prototype.hasOwnProperty.call(PROVIDER_URLS,provider)) return bad('未识别的提供商，请选择自定义兼容服务')
  const base_url = normalizeBaseUrl(text(value.base_url,PROVIDER_URLS[provider],512,'服务地址'))
  const model = text(value.model,'',128,'模型名称')
  const max_tokens = value.max_tokens == null ? null : integer(value.max_tokens,256,256,2000000,'最大输出长度')
  const context_window = value.context_window == null ? null : integer(value.context_window,4096,4096,2000000,'上下文窗口')
  const thinking_budget = integer(value.thinking_budget,1024,1024,7168,'思考预算')
  const token_parameter = value.token_parameter ?? (provider === 'openai' ? 'max_completion_tokens' : 'max_tokens')
  const reasoning_effort = value.reasoning_effort ?? 'auto', thinking_mode = value.thinking_mode ?? 'auto'
  if (!['max_tokens','max_completion_tokens'].includes(token_parameter)) return bad('输出参数名称不受支持')
  if (!EFFORT_OPTIONS[provider].includes(reasoning_effort)) return bad('该提供商不支持此推理选项')
  if (!['auto','enabled','adaptive','disabled'].includes(thinking_mode)) return bad('思考模式不受支持')
  if (provider !== 'anthropic' && thinking_mode !== 'auto') return bad('思考模式仅适用于 Claude Messages 接口')
  if (provider === 'anthropic' && ['auto','disabled'].includes(thinking_mode) && reasoning_effort !== 'auto') return bad('设置推理强度前请选择预算思考或自适应思考')
  if (provider === 'anthropic' && thinking_mode === 'enabled' && max_tokens !== null && thinking_budget >= max_tokens) return bad('思考预算必须小于最大输出长度，为正文留出空间')
  if (max_tokens !== null && context_window !== null && max_tokens >= context_window) return bad('上下文窗口必须大于最大输出长度，为输入留出空间')
  return {provider,base_url,model,max_tokens,context_window,thinking_budget,token_parameter,reasoning_effort,thinking_mode}
}
const aliases: Record<string,string[]> = {
  name:['name','label','AI_CONNECTION_NAME'], provider:['provider','AI_PROVIDER'],
  base_url:['base_url','baseURL','baseUrl','api_base','apiBase','AI_BASE_URL','OPENAI_BASE_URL','OPENAI_API_BASE','BASE_URL'],
  api_key:['api_key','apiKey','key','AI_API_KEY','OPENAI_API_KEY','API_KEY'],
  model:['model','model_id','modelId','AI_MODEL','OPENAI_MODEL','MODEL'],
  max_tokens:['max_tokens','maxTokens','AI_MAX_TOKENS','MAX_TOKENS'],
  context_window:['context_window','contextWindow','AI_CONTEXT_WINDOW','CONTEXT_WINDOW'],
  reasoning_effort:['reasoning_effort','reasoningEffort','AI_REASONING_EFFORT'],
  thinking_mode:['thinking_mode','AI_THINKING_MODE'], thinking_budget:['thinking_budget','AI_THINKING_BUDGET'],
  token_parameter:['token_parameter','AI_TOKEN_PARAMETER'],
}
function parseEnv(source: string): Record<string,string> {
  const values: Record<string,string> = {}
  for (const line of source.split(/\r?\n/)) {
    if (!line.trim() || line.trim().startsWith('#')) continue
    const match = line.match(/^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$/)
    if (!match) return bad('环境配置格式不正确，请使用 KEY=value；不会执行脚本或变量替换')
    let value = match[2] ?? ''
    if (value.startsWith('"')) {
      try {value = JSON.parse(value) as string} catch {return bad('环境配置中的双引号未正确闭合')}
    } else if (value.startsWith("'")) {
      if (!value.endsWith("'")) return bad('环境配置中的单引号未正确闭合')
      value = value.slice(1,-1)
    } else value = value.replace(/\s+#.*$/,'').trim()
    if (typeof value !== 'string' || /\$\{|\$\(|`/.test(value)) return bad('配置中的变量或命令须先替换为实际值')
    values[match[1]!] = value
  }
  return values
}
export function parseConnectionConfig(source: string): {connections:ImportedConnection[]; warnings:string[]} {
  if (new TextEncoder().encode(source).length > 65536) return bad('配置文件不能超过 64 KiB')
  let document: unknown
  try {document = /^[\s\uFEFF]*[\[{]/.test(source) ? JSON.parse(source.replace(/^\uFEFF/,'')) : parseEnv(source)}
  catch (reason) {if (reason instanceof SyntaxError) return bad('JSON 配置无法解析，请检查格式'); throw reason}
  if (object(document) && document.format !== undefined && (document.format !== 'celllens.ai-connections' || document.version !== 1)) return bad('配置文件类型或版本不受支持')
  const entries = Array.isArray(document) ? document : object(document) && Array.isArray(document.connections) ? document.connections : [document]
  if (!entries.length || entries.length > 20) return bad('每次可导入 1–20 组连接')
  const warnings = new Set<string>()
  const connections = entries.map((entry,index) => {
    if (!object(entry)) return bad('每组连接须为 JSON 对象')
    const mapped: Record<string,unknown> = {}
    for (const [field,keys] of Object.entries(aliases)) {
      const key = keys.find(key => Object.prototype.hasOwnProperty.call(entry,key))
      if (key) mapped[field] = entry[key]
    }
    if (!Object.keys(mapped).some(key => ['base_url','provider','model','api_key'].includes(key))) return bad('配置未包含可识别的 API 连接字段')
    if (Object.keys(entry).some(key => !Object.values(aliases).some(keys => keys.includes(key)))) warnings.add('未识别的字段已忽略；仅导入页面支持的连接参数。')
    const preferences = cleanPreferences(mapped as Partial<ModelPreferences>)
    const api_key = text(mapped.api_key,'',4096,'API Key')
    if (api_key && /[^\x21-\x7e]/.test(api_key)) return bad('API Key 格式不正确')
    return {...preferences,api_key,name:text(mapped.name,`导入连接 ${index+1}`,64,'连接名称') || `导入连接 ${index+1}`}
  })
  return {connections,warnings:[...warnings]}
}
export function exportConnectionConfig(connections: (ModelPreferences & {name?:string})[]): string {
  return JSON.stringify({format:'celllens.ai-connections',version:1,connections:connections.map(connection => Object.fromEntries([
    ['name',connection.name ?? '我的 API'], ...fields.map(field => [field,connection[field]]),
  ]))},null,2)
}
export function estimateInputTokens(contents: string[]): number {
  return contents.reduce((sum,content) => sum + Math.ceil(new TextEncoder().encode(content).length/3) + 8,0)
}
